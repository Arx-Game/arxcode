import cloudinary
def consts(request):
    return dict(
        ICON_EFFECTS = dict(
            format="png",
            type="facebook",
            transformation=[
                dict(height=95, width=95, crop="thumb", gravity="face", effect="sepia", radius=20),
                dict(angle=10),
            ]
        ),
        THUMBNAIL = {
            "class": "thumbnail inline", "format": "jpg", "crop": "fill", "height": 150, "width": 150,
        },
        CLOUDINARY_CLOUD_NAME = cloudinary.config().cloud_name
    )
