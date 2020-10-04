from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


def adjust_pagination(
    context,
    page,
    begin_pages=2,
    end_pages=2,
    before_current_pages=4,
    after_current_pages=4,
    page_name="page_obj",
):
    # Digg-like pages
    before = max(page.number - before_current_pages - 1, 0)
    after = page.number + after_current_pages
    begin = list(page.paginator.page_range)[:begin_pages]
    middle = list(page.paginator.page_range)[before:after]
    end = list(page.paginator.page_range)[-end_pages:]
    last_page_number = end[-1]

    def collides(firstlist, secondlist):
        """Returns true if lists collides (have same entries)

        >>> collides([1,2,3,4],[3,4,5,6,7])
        True
        >>> collides([1,2,3,4],[5,6,7])
        False
        """
        return any(item in secondlist for item in firstlist)

    # If middle and end has same entries, then end is what we want
    if collides(middle, end):
        end = range(max(page.number - before_current_pages, 1), last_page_number + 1)

        middle = []

    # If begin and middle ranges has same entries, then begin is what we want
    if collides(begin, middle):
        begin = range(1, min(page.number + after_current_pages, last_page_number) + 1)

        middle = []

    # If begin and end has same entries then begin is what we want
    if collides(begin, end):
        begin = range(1, last_page_number + 1)
        end = []

    context.update(
        {
            page_name: page,
            "%s_begin" % page_name: begin,
            "%s_middle" % page_name: middle,
            "%s_end" % page_name: end,
        }
    )

    return context


class LimitPageMixin(object):
    """
    Will adjust the pages created by paginator to have a range,
    and adds more lists to the context that contains the beginning,
    middle, and end of the pages if they don't overlap with one
    another. The default name for the page object given by paginator
    is 'page_obj', and it will create page_obj_begin, page_obj_middle,
    and page_obj_end, respectively. To add additional pages, put them
    in the 'additional_pages' dict, which is a mapping of page names to
    a tuple of a callable that returns the queryset and the GET name that
    returns the current page for that object.
    """

    default_page_name = "page_obj"
    # dictionary of context names to a callable that returns the queryset to be used
    additional_pages = {}
    paginate_by = 20
    begin_pages = 2
    end_pages = 2
    before_current_pages = 4
    after_current_pages = 4

    def get_context_data(self, **kwargs):
        context = super(LimitPageMixin, self).get_context_data(**kwargs)
        if self.default_page_name:
            default_page = context[self.default_page_name]
            context = adjust_pagination(
                context=context,
                page=default_page,
                begin_pages=self.begin_pages,
                end_pages=self.end_pages,
                before_current_pages=self.before_current_pages,
                after_current_pages=self.after_current_pages,
                page_name=self.default_page_name,
            )
        for page_name in self.additional_pages:
            # get the queryset we'll paginate
            qs = getattr(self, self.additional_pages[page_name][0])()
            # get the number of the requested page from GET request
            requested_page_num = self.request.GET.get(
                self.additional_pages[page_name][1]
            )
            paged_qs = Paginator(qs, self.paginate_by)
            try:
                page = paged_qs.page(requested_page_num)
            except PageNotAnInteger:
                page = paged_qs.page(1)
            except EmptyPage:
                page = paged_qs.page(paged_qs.num_pages)
            context = adjust_pagination(
                context,
                page,
                begin_pages=self.begin_pages,
                end_pages=self.end_pages,
                before_current_pages=self.before_current_pages,
                after_current_pages=self.after_current_pages,
                page_name=page_name,
            )
        return context
