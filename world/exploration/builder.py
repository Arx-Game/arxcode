"""
This is the Builder library that will actually generate a Shardhaven
layout maze.  When a builder has generated a maze, casting it to a
string will provide an ASCII representation of the maze (for easy
debugging).  These mazes are not persisted in and of themselves,
but will be used by the Shardhaven generator to make a layout, after
which a ShardhavenLayout will be made.
"""

from random import shuffle, randint


class BuilderGridSquare(object):

    def __init__(self):

        self.wall = True
        self.visited = False
        self.deadend = False

    def __str__(self):
        return "WALL" if self.wall else "FLOOR"


class Builder(object):

    NORTH = 0
    EAST = 1
    SOUTH = 2
    WEST = 3
    dir_conversion = {
        NORTH: (0, -2),
        EAST: (2, 0),
        SOUTH: (0, 2),
        WEST: (-2, 0)
    }

    def __init__(self, x_dim=9, y_dim=9, x_start=None, y_start=None):
        if x_dim % 2 == 0 or y_dim % 2 == 0:
            raise ValueError("Dimensions must be odd numbers.")

        self.grid = [[BuilderGridSquare() for y in range(y_dim)] for x in range(x_dim)]
        self.x_dim = x_dim
        self.y_dim = y_dim

        if not x_start:
            x_start = 1 + (2 * randint(0, (x_dim / 2) - 1))
        if not y_start:
            y_start = 1 + (2 * randint(0, (y_dim / 2) - 1))

        self.controller_x = x_start
        self.x_start = x_start
        self.controller_y = y_start
        self.y_start = y_start
        self.grid[x_start][y_start].wall = False

    def backstep(self, direction=NORTH):
        move = self.dir_conversion.get(direction)
        x_by = move[0]
        y_by = move[1]

        test_x = self.controller_x + x_by
        test_y = self.controller_y + y_by

        if test_x < 0 or test_x >= self.x_dim:
            return False, self.controller_x, self.controller_y
        if test_y < 0 or test_y >= self.y_dim:
            return False, self.controller_x, self.controller_y

        if test_x == self.x_start and test_y == self.y_start:
            return False, self.controller_x, self.controller_y

        test_x2 = self.controller_x + (x_by / 2)
        test_y2 = self.controller_y + (y_by / 2)

        if self.grid[test_x][test_y].deadend or self.grid[test_x2][test_y2].deadend:
            return False, self.controller_x, self.controller_y

        if self.grid[test_x][test_y].wall or self.grid[test_x2][test_y2].wall:
            return False, self.controller_x, self.controller_y

        self.grid[self.controller_x][self.controller_y].visited = True
        self.grid[test_x][test_y].visited = True
        self.grid[test_x2][test_y2].visited = True

        return True, test_x, test_y

    def step(self, direction=NORTH):
        move = self.dir_conversion.get(direction)
        x_by = move[0]
        y_by = move[1]

        test_x = self.controller_x + x_by
        test_y = self.controller_y + y_by

        if test_x < 0 or test_x >= self.x_dim:
            return False, self.controller_x, self.controller_y
        if test_y < 0 or test_y >= self.y_dim:
            return False, self.controller_x, self.controller_y

        test_x2 = self.controller_x + (x_by / 2)
        test_y2 = self.controller_y + (y_by / 2)

        if not self.grid[test_x][test_y].wall or not self.grid[test_x2][test_y2].wall:
            return False, self.controller_x, self.controller_y

        self.grid[test_x][test_y].wall = False
        self.grid[test_x2][test_y2].wall = False

        return True, test_x, test_y

    def build_step(self):
        directions = [self.NORTH, self.EAST, self.SOUTH, self.WEST]
        shuffle(directions)

        found = False
        for direction in directions:
            found, self.controller_x, self.controller_y = self.step(direction)
            if found:
                return False

        if not found:
            self.grid[self.controller_x][self.controller_y].visited = True
            self.grid[self.controller_x][self.controller_y].deadend = True
            shuffle(directions)
            for direction in directions:
                found, self.controller_x, self.controller_y = self.backstep(direction)
                if found:
                    return False

        return True

    def build(self):
        done = False
        while not done:
            done = self.build_step()

    def __str__(self):

        string = ""
        for y in range(self.y_dim):
            for x in range(self.x_dim):
                if x == self.x_start and y == self.y_start:
                    string += "|w*|n"
                elif self.grid[x][y].wall:
                    string += "|[B|B#|n"
                else:
                    string += " "
            string += "|n\n"

        return string
