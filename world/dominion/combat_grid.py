"""
Combat Grid for positional combat.
"""
import traceback

class CombatGrid(object):
    def __init__(self):
        # dictionary of 3-tuple of coords to list of actors
        self.actors = {(0,0,0): []}
        # set of squares that provide cover
        self.cover = {}

    def move_actor(self, actor, newpos):
        old = actor.position
        self.actors[old].remove(actor)
        self.addactor(actor, newpos)
        
    def get_actors(self, x=0, y=0, z=0):
        return self.actors.get((x,y,z), [])
    
    def check_cover(self, x=0, y=0, z=0):
        return self.cover.get((x,y,z), None)
    
    def add_actor(self, actor, newpos=None):
        """
        If a new position is given, update actor to be at that
        current position and add it. Otherwise, add actor at its
        currently recorded position.
        """
        if not newpos:
            newpos = actor.position
        else:
            actor.position = newpos
        if not self.actors.get(newpos, None):
            self.actors[newpos] = []
        self.actors[newpos].append(actor)
    
    # to do - AE effects from radius, etc

class PositionActor(object):
    def __init__(self, grid=None):
        self.grid = grid
        self.x_pos = 0
        self.y_pos = 0
        self.z_pos = 0
        self.flying = False
        
    def _get_position(self):
        return self.x_pos, self.y_pos, self.z_pos
    def _set_position(self, pos):
        try:
            x,y,z = pos
            x = int(x)
            y = int(y)
            z = int(z)
        except ValueError:
            print "ERROR: Did not give 3 arguments to set position: %s" % str(pos)
            try:
                if len(pos) < 2:
                    x = int(pos[0])
                if len(pos) < 3:
                    y = int(pos[1])
                if len(pos) > 3:
                    z = int(pos[2])
            except:
                print "Arguments also cannot be cast to int for pos: %s" % str(pos)
                print "Falling back to starting position."
                x = self.x_pos
                y = self.y_pos
                z = self.z_pos
        except TypeError:
            print "ERROR:: Invalid type called for set_position: %s is %s" % (str(pos), type(pos))
            print "Falling back to starting position."
            x = self.x_pos
            y = self.y_pos
            z = self.z_pos
        self.x_pos = x
        self.y_pos = y
        self.z_pos = z
    position = property(_get_position, _set_position)
    
    def move(self, x=0, y=0, z=0):
        new_pos = (x,y,z)
        # grid.move_actor will update our position for us
        try:
            self.grid.move_actor(self, new_pos)
        except AttributeError:
            print "ERROR: PositionActor.move() called before grid defined."
            traceback.print_exc()
        
    def check_distance_to_actor(self, actor):
        x,y,z = actor.position
        return self.check_distance_to_position(x,y,z)
        
    def check_distance_to_position(self, x=0, y=0, z=0):
        distance = abs(x - self.x_pos)
        y_dist = abs(y - self.y_pos)
        if y_dist > distance: distance = y_dist
        z_dist = abs(z - self.z_pos)
        if z_dist > distance: distance = z_dist
        return distance
    
    def move_toward_actor(self, targ, max_dist=10):
        x,y,z = targ.position
        self.move_toward_position(x, y, z, max_dist)
        
    def move_toward_position(self, x=0, y=0, z=0, max_dist=10):
        dist = self.check_distance_to_position(x,y,z)
        if dist < max_dist:
            z = self.z_pos
            if self.flying:
                z = targ.z_pos
            self.move(x=targ.x_pos, y=targ.y_pos, z=z)
            return
        x,y,z = targ.position
        new_x = self.get_coord(self.x_pos, x, max_dist)
        new_y = self.get_coord(self.y_pos, y, max_dist)
        new_z = self.z_pos
        if self.flying:
            new_z = self.get_coord(self.z_pos, z, max_dist)
        self.move(x=new_x, y=new_y, z=new_z)
        
        
    def get_coord(self, s_coord, t_coord, max_dist=10):
        step = 1
        # if the target is lower on the axis, we're going down, not up
        if t_coord < s_coord:
            step *= -1
        dist = abs(t_coord - s_coord)
        # possible individual axes could be less than max distance.
        if dist < max_dist:
            max_dist = dist
        max_dist *= step
        s_coord += max_dist
        return s_coord


