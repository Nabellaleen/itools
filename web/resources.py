# -*- coding: UTF-8 -*-
# Copyright (C) 2007 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2007-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2008 David Versmisse <david.versmisse@itaapy.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Import from itools
from itools.uri import Path
from access import AccessControl
from views import BaseView


class Resource(object):
    """A Resource is a base object supporting the HTTP protocol and the access
    control API.
    """

    #######################################################################
    # API / Private
    #######################################################################
    def _has_resource(self, name):
        """Default implementation, may be overriden for a better performance.
        """
        try:
            self._get_resource(name)
        except LookupError:
            return False
        return True


    def _get_names(self):
        raise NotImplementedError


    def _get_resource(self, name):
        raise LookupError


    #######################################################################
    # API / Tree
    #######################################################################
    def get_abspath(self):
        if self.parent is None:
            return Path('/')
        parent_path = self.parent.get_abspath()

        return parent_path.resolve2(self.name)

    abspath = property(get_abspath, None, None, '')


    def get_canonical_path(self):
        if self.parent is None:
            return Path('/')
        parent_path = self.parent.get_canonical_path()

        return parent_path.resolve2(self.name)


    def get_real_object(self):
        cpath = self.get_canonical_path()
        if cpath == self.get_abspath():
            return self
        return self.get_resource(cpath)


    def get_root(self):
        if self.parent is None:
            return self
        return self.parent.get_root()


    def get_pathto(self, handler):
        return self.get_abspath().get_pathto(handler.get_abspath())


    def has_resource(self, path):
        if not isinstance(path, Path):
            path = Path(path)

        # If path is "/" or "."
        if len(path) == 0:
            return True

        path, name = path[:-1], path[-1]
        try:
            container = self.get_resource(path)
        except LookupError:
            return False

        return container._has_resource(name)


    def get_names(self, path='.'):
        object = self.get_resource(path)
        return object._get_names()


    def get_resource(self, path):
        if not isinstance(path, Path):
            path = Path(path)

        if path.is_absolute():
            here = self.get_root()
        else:
            here = self

        while path and path[0] == '..':
            here = here.parent
            path = path[1:]

        for name in path:
            object = here._get_resource(name)
            object.parent = here
            object.name = name
            here = object

        return here


    def get_resources(self, path='.'):
        here = self.get_resource(path)
        for name in here._get_names():
            object = here._get_resource(name)
            object.parent = here
            object.name = name
            yield object


    def set_resource(self, path, object):
        raise NotImplementedError


    def del_resource(self, path):
        raise NotImplementedError


    def copy_resource(self, source, target):
        raise NotImplementedError


    def move_resource(self, source, target):
        raise NotImplementedError


    def traverse_objects(self):
        raise NotImplementedError


    #######################################################################
    # API / Views
    #######################################################################
    default_view_name = None


    def get_default_view_name(self):
        return self.default_view_name


    def get_view(self, name, query=None):
        # To define a default view, override this
        if name is None:
            name = self.get_default_view_name()
            if name is None:
                return None

        # Explicit view, defined by name
        view = getattr(self, name, None)
        if view is None or not isinstance(view, BaseView):
            return None

        return view

    #######################################################################
    # API / Security
    #######################################################################
    def get_access_control(self):
        resource = self
        while resource is not None:
            if isinstance(resource, AccessControl):
                return resource
            resource = resource.parent

        return None



class RootResource(AccessControl, Resource):
    """The RootResource is the main entry point of the Web application.
    Responsible for traversal, user retrieval, and error pages.  It is a
    handler of type Folder so check out the Handler and Folder API.
    """

    def get_user(self, username):
        """Return an object representing the user named after the username,
        or 'None'.  The nature of the object, the location of the storage
        and the retrieval of the data remain at your discretion. The only
        requirements are the "name" attribute, and the "authenticate" method
        with a "password" parameter.
        """
        return None


    #######################################################################
    # API / Publishing
    #######################################################################
    def before_traverse(self, context):
        """Pre-publishing process.
        Possible actions are language negotiation, etc.
        """
        pass


    def after_traverse(self, context):
        """Post-publishing process.
        Possible actions are wrapping the body into a template, etc."""
        pass


    #######################################################################
    # API / Error Pages
    #######################################################################
    def unauthorized(self, context):
        """Called on status 401 for replacing the body by an error page."""
        return '401 Unauthorized'


    def forbidden(self, context):
        """Called on status 403 for replacing the body by an error page."""
        return '403 Forbidden'


    def not_found(self, context):
        """Called on status 404 for replacing the body by an error page."""
        return '404 Not Found'


    def internal_server_error(self, context):
        """Called on status 500 for replacing the body by an error page."""
        return '500 Internal Server Error'