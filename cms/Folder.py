# -*- coding: UTF-8 -*-
# Copyright (C) 2003-2006 Juan David Ibáñez Palomar <jdavid@itaapy.com>
#                    2005 Alexandre Fernandez <alex@itaapy.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA

# Import from the Standard Library
import marshal
from string import Template
import urllib
import zlib

# Import from itools
from itools.i18n.locale_ import format_datetime
from itools.uri import Path, get_reference
from itools.catalog import queries
from itools.datatypes import Boolean, FileName, Integer, Unicode
from itools import vfs
from itools.handlers.Folder import Folder as BaseFolder
from itools.handlers.registry import get_handler_class
from itools.handlers.Text import Text
from itools import i18n
from itools.stl import stl
from itools.web import get_context

# Import from itools.cms
import File
from Handler import Handler
from binary import Image
from catalog import CatalogAware
from handlers import Lock, Metadata, ListOfUsers
from ical import CalendarAware
from versioning import VersioningAware
from workflow import WorkflowAware
from utils import checkid, reduce_string
import widgets
from registry import register_object_class, get_object_class



class Folder(Handler, BaseFolder, CalendarAware):

    #########################################################################
    # Class metadata
    #########################################################################
    class_id = 'folder'
    class_version = '20040625'
    class_title = u'Folder'
    class_description = u'Organize your files and documents with folders.'
    class_icon16 = 'images/Folder16.png'
    class_icon48 = 'images/Folder48.png'
    class_views = [
        ['browse_content?mode=thumbnails',
         'browse_content?mode=list',
         'browse_content?mode=image'],
        ['new_resource_form'],
        ['edit_metadata_form']]


    search_criteria =  [
        {'id': 'title', 'title': u"Title"},
        {'id': 'text', 'title': u"Text"},
        {'id': 'name', 'title': u"Name"},
    ]


    #########################################################################
    # Aggregation relationship (what a generic folder can contain)
    class_document_types = []

    __fixed_handlers__ = []


    @classmethod
    def register_document_type(cls, handler_class):
        cls.class_document_types.append(handler_class)


    def get_document_types(self):
        return self.class_document_types


    @classmethod
    def new_instance_form(cls):
        namespace = {'class_id': cls.class_id,
                     'class_title': cls.gettext(cls.class_title)}

        root = get_context().root
        handler = root.get_handler('ui/Folder_new_instance.xml')
        return stl(handler, namespace)


    #######################################################################
    # Traverse
    #######################################################################
    GET__access__ = True
    def GET(self, context):
        # Try index
        for name in ['index.xhtml', 'index.html']:
            if self.has_handler(name):
                return context.uri.resolve2(name)

        return Handler.GET(self, context)


    def _get_handler(self, segment, uri):
        name = segment.name
        # Metadata
        if name.endswith('.metadata'):
            return Metadata(uri)
        # Locks
        if name.endswith('.lock'):
            return Lock(uri)
        # XXX ListOfUsers (to be removed in 0.16)
        if name.startswith('.') and name.endswith('.users'):
            return ListOfUsers(uri)

        # cms objects
        if self.has_handler('%s.metadata' % name):
            metadata = self.get_handler('%s.metadata' % name)
            format = metadata.get_property('format')
            cls = get_object_class(format)
            return cls(uri)

        # XXX For now UI objects are like cms objects
        from skins import UI
        x = self
        while x:
            if isinstance(x, UI):
                format = vfs.get_mimetype(uri)
                cls = get_object_class(format)
                return cls(uri)
            x = x.parent

        # Anything else is a bare handler
        cls = get_handler_class(uri)
        return cls(uri)


    def _get_handler_names(self):
        names = BaseFolder._get_handler_names(self)
        for name in names:
            if not name.startswith('.'):
                name, type, language = FileName.decode(name)
                if language is not None:
                    name = FileName.encode((name, type, None))
                    names.append(name)

        return names


    def _get_virtual_handler(self, segment):
        name = segment.name

        languages = [ x.split('.')[-1] for x in self.cache
                      if x.startswith(name) ]
        languages = [ x for x in languages if x in i18n.languages ]

        if languages:
            # Get the best variant
            context = get_context()

            if context is None:
                language = None
            else:
                request = context.request
                language = request.accept_language.select_language(languages)

            # By default use whatever variant
            # (XXX we need a way to define the default)
            if language is None:
                language = languages[0]
            return self.get_handler('%s.%s' % (name, language))

        return BaseFolder._get_virtual_handler(self, segment)


    def before_set_handler(self, segment, handler, format=None, id=None,
                           move=False, **kw):
        name = segment.name
        if not isinstance(handler, Handler):
            return
        if name.startswith('.'):
            return

        # Set metadata
        metadata = handler.get_metadata()
        if metadata is None:
            metadata = self.build_metadata(handler, format=format, **kw)
        self.set_handler('%s.metadata' % name, metadata)


    def after_set_handler(self, segment, handler, format=None, id=None,
                          move=False, **kw):
        from root import Root

        name = segment.name
        if not isinstance(handler, Handler):
            return
        if name.startswith('.'):
            return

        root = self.get_root()
        if isinstance(root, Root):
            # Index
            handler = self.get_handler(segment)
            if isinstance(handler, Folder):
                for x, context in handler.traverse2():
                    if x.real_handler is not None:
                        context.skip = True
                    else:
                        if isinstance(x, CatalogAware):
                            root.index_handler(x)
            else:
                root.index_handler(handler)
            # Store history
            if move is False:
                if isinstance(handler, Folder):
                    for x, context in handler.traverse2():
                        if x.real_handler is not None:
                            context.skip = True
                        else:
                            if isinstance(x, VersioningAware):
                                x.commit_revision()
                    else:
                        if isinstance(handler, VersioningAware):
                            handler.commit_revision()


    def on_del_handler(self, segment):
        from root import Root

        name = segment.name
        if (name.startswith('.')
            or name.endswith('.metadata')
            or name.endswith('.lock')):
            return

        handler = self.get_handler(segment)
        # Unindex
        root = self.get_root()
        if isinstance(root, Root):
            if isinstance(handler, Folder):
                for x, context in handler.traverse2():
                    if x.real_handler is None:
                        root.unindex_handler(x)
                    else:
                        context.skip = True
            else:
                root.unindex_handler(handler)

        # Remove metadata
        self.del_handler('%s.metadata' % name)


    def build_metadata(self, handler, owner=None, format=None, **kw):
        """Return a Metadata object with sensible default values."""
        if owner is None:
            owner = ''
            context = get_context()
            if context is not None:
                if context.user is not None:
                    owner = context.user.name

        if format is None:
            format = handler.class_id

        if isinstance(handler, WorkflowAware):
            kw['state'] = handler.workflow.initstate

        return Metadata(handler_class=handler.__class__, owner=owner,
                        format=format, **kw)


    #######################################################################
    # API
    #######################################################################
    def search_handlers(self, path='.', format=None, state=None,
                        handler_class=None):
        container = self.get_handler(path)

        for name in container.get_handler_names():
            # Skip hidden handlers
            if name.startswith('.'):
                continue
            if name.endswith('.metadata'):
                continue

            filename, type, language = FileName.decode(name)
            if language is not None:
                continue

            handler = container.get_handler(name)
            if handler_class is not None:
                if not isinstance(handler, handler_class):
                    continue

            get_property = getattr(handler, 'get_property', lambda x: None)
            if format is None or get_property('format') == format:
                if state is None:
                    yield handler
                else:
                    handler_state = get_property('state')
                    if handler_state == state:
                        yield handler


    #######################################################################
    # User interface
    #######################################################################
    def get_subviews(self, name):
        if name == 'new_resource_form':
            subviews = []
            for cls in self.get_document_types():
                id = cls.class_id
                ref = 'new_resource_form?type=%s' % urllib.quote_plus(id)
                subviews.append(ref)
            return subviews
        return Handler.get_subviews(self, name)


    def new_resource_form__sublabel__(self, **kw):
        type = kw.get('type')
        for cls in self.get_document_types():
            if cls.class_id == type:
                return cls.class_title
        return u'New Resource'


    #######################################################################
    # Browse
    def get_human_size(self):
        names = self.get_handler_names()
        names = [ x for x in names if (x[0] != '.' and x[-9:] != '.metadata') ]
        size = len(names)

        str = self.gettext('$n obs')
        return Template(str).substitute(n=size)


    def _browse_namespace(self, object, icon_size):
        line = {}
        id = str(self.get_pathto(object))
        line['id'] = id
        line['title_or_name'] = object.title_or_name
        firstview = object.get_firstview()
        if firstview is None:
            href = None
        else:
            href = '%s/;%s' % (id, firstview)
        line['name'] = (id, href)
        line['format'] = self.gettext(object.class_title)
        line['title'] = object.get_property('dc:title')
        # Filesystem information
        uri = object.uri
        line['mtime'] = vfs.get_mtime(uri)
        # Titles
        line['short_title'] = reduce_string(object.title_or_name, 12, 40)
        # The size
        line['size'] = object.get_human_size()
        # The url
        line['href'] = href
        # The icon
        path_to_icon = object.get_path_to_icon(icon_size, from_handler=self)
        if path_to_icon.startswith(';'):
            path_to_icon = Path('%s/' % object.name).resolve(path_to_icon)
        line['img'] = path_to_icon
        # The modification time
        accept = get_context().request.accept_language
        line['mtime'] = format_datetime(object.mtime, accept=accept)
        # The workflow state
        line['workflow_state'] = ''
        if isinstance(object, WorkflowAware):
            state = object.get_state()
            line['workflow_state'] = self.gettext(state['title'])
        # Objects that should not be removed/renamed/etc
        line['checkbox'] = object.name not in self.__fixed_handlers__

        return line


    def browse_namespace(self, icon_size, sortby=['title_or_name'],
                         sortorder='up', batchstart=0, batchsize=20,
                         query=None, results=None):
        context = get_context()
        # Load variables from the request
        start = context.get_form_value('batchstart', type=Integer,
                                       default=batchstart)
        size = context.get_form_value('batchsize', type=Integer,
                                      default=batchsize)

        # Search
        root = context.root
        if results is None:
            catalog = root.get_handler('.catalog')
            results = catalog.search(query)
            reverse = (sortorder == 'down')
            documents = results.get_documents(sort_by=sortby, reverse=reverse,
                                              start=start, size=batchsize)

        # Get the handlers, check security
        user = context.user
        handlers = []
        for document in documents:
            handler = root.get_handler(document.abspath)
            ac = handler.get_access_control()
            if ac.is_allowed_to_view(user, handler):
                handlers.append(handler)

        # Get the handler for the visible documents and extracts values
        objects = []
        for handler in handlers:
            line = self._browse_namespace(handler, icon_size)
            objects.append(line)

        # Build namespace
        namespace = {}
        total = results.get_n_documents()
        namespace['total'] = total
        namespace['objects'] = objects

        # The batch
        namespace['batch'] = widgets.batch(context.uri, start, size, total)

        return namespace


    def browse_thumbnails(self, context):
        context.set_cookie('browse', 'thumb')

        query = queries.Equal('parent_path', self.get_abspath())
        namespace = self.browse_namespace(48, query=query)

        handler = self.get_handler('/ui/Folder_browse_thumbnails.xml')
        return stl(handler, namespace)


    def browse_list(self, context, sortby=['title_or_name'], sortorder='up'):
        context.set_cookie('browse', 'list')

        # Get the form values
        get_form_value = context.get_form_value
        term = get_form_value('search_term', type=Unicode)
        term = term.strip()
        field = get_form_value('search_field')
        search_subfolders = get_form_value('search_subfolders', type=Boolean,
                                           default=False)

        sortby = context.get_form_values('sortby', default=sortby)
        sortorder = context.get_form_value('sortorder', sortorder)

        # Build the query
        abspath = self.get_abspath()
        if term:
            if search_subfolders is True:
                query = queries.Equal('paths', abspath)
            else:
                query = queries.Equal('parent_path', abspath)
            query = queries.And(query, queries.Phrase(field, term))
        else:
            query = queries.Equal('parent_path', abspath)

        # Build the namespace
        namespace = self.browse_namespace(16, query=query, sortby=sortby,
                                          sortorder=sortorder)
        namespace['search_term'] = term
        namespace['search_subfolders'] = search_subfolders
        namespace['search_fields'] = [
            {'id': x['id'], 'title': self.gettext(x['title']),
             'selected': x['id'] == field or None}
            for x in self.get_search_criteria() ]

        # The column headers
        columns = [
            ('name', u'Name'), ('title', u'Title'), ('format', u'Type'),
            ('mtime', u'Date'), ('size', u'Size'),
            ('workflow_state', u'State')]

        # Actions
        user = context.user
        ac = self.get_access_control()
        actions = []
        if namespace['total']:
            actions = [
                ('remove', u'Remove', 'button_delete',
                 'return confirmation();'),
                ('rename_form', u'Rename', 'button_rename', None),
                ('copy', u'Copy', 'button_copy', None),
                ('cut', u'Cut', 'button_cut', None)]
            actions = [
                x for x in actions if ac.is_access_allowed(user, self, x[0]) ]
        if context.has_cookie('ikaaro_cp'):
            if ac.is_access_allowed(user, self, 'paste'):
                actions.append(('paste', u'Paste', 'button_paste', None))

        # Go!
        namespace['table'] = widgets.table(
            columns, namespace['objects'], sortby, sortorder, actions,
            self.gettext)

        handler = self.get_handler('/ui/Folder_browse_list.xml')
        return stl(handler, namespace)


    def browse_image(self, context):
        selected_image = context.get_form_value('selected_image')
        selected_index = None

        # check selected image
        if selected_image is not None:
            path = Path(selected_image)
            selected_image = path[-1].name
            if not selected_image in self.get_handler_names():
                selected_image = None

        # look up available images
        query = queries.Equal('parent_path', self.get_abspath())
        namespace = self.browse_namespace(48, query=query, batchsize=0)
        objects = []
        offset = 0
        for index, object in enumerate(namespace['objects']):
            name = object['name']
            if isinstance(name, tuple):
                name = name[0]
            handler = self.get_handler(name)
            if not isinstance(handler, Image):
                offset = offset + 1
                continue
            if selected_image is None:
                selected_image = name
            if selected_image == name:
                selected_index = index - offset
            object['name'] = name
            objects.append(object)

        namespace['objects'] = objects

        # selected image namespace
        if selected_image is None:
            namespace['selected'] = None
        else:
            image = self.get_handler(selected_image)
            selected = {}
            selected['title_or_name'] = image.title_or_name
            selected['description'] = image.get_property('dc:description')
            selected['url'] = '%s/;%s' % (image.name, image.get_firstview())
            selected['preview'] = '%s/;icon48?height=320&width=320' \
                                  % image.name
            width, height = image.get_size()
            selected['width'] = width
            selected['height'] = height
            selected['format'] = image.get_format()
            if selected_index == 0:
                selected['previous'] = None
            else:
                previous = objects[selected_index - 1]['name']
                selected['previous'] = ';%s?selected_image=%s' % (
                        context.method, previous)
            if selected_index == (len(objects) - 1):
                selected['next'] = None
            else:
                next = objects[selected_index + 1]['name']
                selected['next'] = ';%s?selected_image=%s' % (context.method,
                        next)
            namespace['selected'] = selected

        handler = self.get_handler('/ui/Folder_browse_image.xml')
        return stl(handler, namespace)


    remove__access__ = 'is_allowed_to_remove'
    def remove(self, context):
        ids = context.get_form_values('ids')
        if not ids:
            return context.come_back(u'No objects selected.')

        removed = []
        not_allowed = []

        user = context.user
        for name in ids:
            handler = self.get_handler(name)
            ac = handler.get_access_control()
            if ac.is_allowed_to_remove(user, handler):
                # Remove handler
                self.del_handler(name)
                removed.append(name)
            else:
                not_allowed.append(name)

        return context.come_back(
            u'Objects removed: $objects.', objects=', '.join(removed))


    rename_form__access__ = 'is_allowed_to_move'
    def rename_form(self, context):
        ids = context.get_form_values('ids')
        # Filter names which the authenticated user is not allowed to move
        handlers = [ self.get_handler(x) for x in ids ]
        ac = self.get_access_control()
        names = [ x.name for x in handlers
                  if ac.is_allowed_to_move(context.user, x) ]

        # Check input data
        if not names:
            return context.come_back(u'No objects selected.')

        # XXX Hack to get rename working. The current user interface
        # forces the rename_form to be called as a form action, hence
        # with the POST method, but it should be a GET method. Maybe
        # it will be solved after the needed folder browse overhaul.
        if context.request.method == 'POST':
            ids_list = '&'.join([ 'ids=%s' % x for x in names ])
            return get_reference(';rename_form?%s' % ids_list)

        # Build the namespace
        namespace = {}
        namespace['objects'] = []
        for real_name in names:
            name, extension, language = FileName.decode(real_name)
            namespace['objects'].append({'real_name': real_name, 'name': name})

        # Process the template
        handler = self.get_handler('/ui/Folder_rename.xml')
        return stl(handler, namespace)


    rename__access__ = 'is_allowed_to_move'
    def rename(self, context):
        names = context.get_form_values('names')
        new_names = context.get_form_values('new_names')
        # Process input data
        for i, old_name in enumerate(names):
            xxx, extension, language = FileName.decode(old_name)
            new_name = FileName.encode((new_names[i], extension, language))
            new_name = checkid(new_name)
            if new_name is None:
                # Invalid name
                return context.come_back(
                    u'The document name contains illegal characters,'
                    u' choose another one.')
            # Rename
            if new_name != old_name:
                handler = self.get_handler(old_name)
                handler_metadata = handler.get_metadata()

                # XXX itools should provide an API to copy and move handlers
                self.set_handler(new_name, handler, move=True)
                self.del_handler('%s.metadata' % new_name)
                self.set_handler('%s.metadata' % new_name, handler_metadata)
                self.del_handler(old_name)

        message = u'Objects renamed.'
        return context.come_back(message, goto=';browse_content')


    copy__access__ = 'is_allowed_to_copy'
    def copy(self, context):
        ids = context.get_form_values('ids')
        # Filter names which the authenticated user is not allowed to copy
        handlers = [ self.get_handler(x) for x in ids ]
        ac = self.get_access_control()
        names = [ x.name for x in handlers
                  if ac.is_allowed_to_copy(context.user, x) ]

        if not names:
            return context.come_back(u'No objects selected.')

        path = self.get_abspath()
        cp = (False, [ '%s/%s' % (path, x) for x in names ])
        cp = urllib.quote(zlib.compress(marshal.dumps(cp), 9))
        context.set_cookie('ikaaro_cp', cp, path='/')

        return context.come_back(u'Objects copied.')


    cut__access__ = 'is_allowed_to_move'
    def cut(self, context):
        ids = context.get_form_values('ids')
        # Filter names which the authenticated user is not allowed to move
        handlers = [ self.get_handler(x) for x in ids ]
        ac = self.get_access_control()
        names = [ x.name for x in handlers
                  if ac.is_allowed_to_move(context.user, x) ]

        if not names:
            return context.come_back(u'No objects selected.')

        path = self.get_abspath()
        cp = (True, [ '%s/%s' % (path, x) for x in names ])
        cp = urllib.quote(zlib.compress(marshal.dumps(cp), 9))
        context.set_cookie('ikaaro_cp', cp, path='/')

        return context.come_back(u'Objects cut.')


    paste__access__ = 'is_allowed_to_add'
    def paste(self, context):
        cp = context.get_cookie('ikaaro_cp')
        if cp is not None:
            root = context.root
            allowed_types = tuple(self.get_document_types())
            cut, paths = marshal.loads(zlib.decompress(urllib.unquote(cp)))
            for path in paths:
                handler = root.get_handler(path)
                if isinstance(handler, allowed_types):
                    name = handler.name
                    # Find a non used name
                    # XXX ROBLES To be tested carefully and optimized
                    while self.has_handler(name):
                        name = name.split('.')
                        id = name[0].split('_')
                        index = id[-1]
                        try:   # tests if id ends with a number
                            index = int(index)
                        except ValueError:
                            id.append('copy_1')
                        else:
                            try:  # tests if the pattern is '_copy_x'
                               if id[-2] == 'copy':
                                  index = str(index + 1) # increment index
                                  id[-1] = index
                               else:
                                  id.append('copy_1')
                            except IndexError:
                               id.append('copy_1')
                            else:
                               pass
                        id = '_'.join(id)
                        name[0] = id
                        name = '.'.join(name)
                    # Unicode is not a valid Zope id
                    name = str(name)
                    # Add it here
                    if cut is True:
                        self.set_handler(name, handler, move=True)
                        # Remove original
                        container = handler.parent
                        container.del_handler(name)
                    else:
                        self.set_handler(name, handler)
                        # Fix metadata properties
                        handler = self.get_handler(name)
                        metadata = handler.metadata
                        # Fix state
                        if isinstance(handler, WorkflowAware):
                            metadata.set_property('state', handler.workflow.initstate)
                        # Fix owner
                        metadata.set_property('owner', context.user.name)

        return context.come_back(u'Objects pasted.')


    browse_content__access__ = 'is_allowed_to_view'
    browse_content__label__ = u'Contents'

    def browse_content__sublabel__(self, **kw):
        mode = kw.get('mode', 'thumbnails')
        return {'thumbnails': u'As Icons',
                'list': 'As List',
                'image': 'As Image Gallery'}[mode]

    def browse_content(self, context):
        mode = context.get_form_value('mode')
        if mode is None:
            mode = context.get_cookie('browse_mode')
            # Default
            if mode is None:
                mode = 'thumbnails'
        else:
            context.set_cookie('browse_mode', mode)

        method = getattr(self, 'browse_%s' % mode)
        return method(context)


    #######################################################################
    # Add / New Resource
    new_resource_form__access__ = 'is_allowed_to_add'
    new_resource_form__label__ = u'Add'
    def new_resource_form(self, context):
        type = context.get_form_value('type')
        if type is None:
            # Build the namespace
            namespace = {}
            namespace['types'] = []

            for handler_class in self.get_document_types():
                type_ns = {}
                gettext = handler_class.gettext
                format = urllib.quote(handler_class.class_id)
                type_ns['format'] = format
                icon = handler_class.class_icon48
                type_ns['icon'] = self.get_pathtoroot() + 'ui/' + icon
                title = handler_class.class_title
                type_ns['title'] = gettext(title)
                description = handler_class.class_description
                type_ns['description'] = gettext(description)
                type_ns['url'] = ';new_resource_form?type=' + format
                namespace['types'].append(type_ns)

            handler = self.get_handler('/ui/Folder_new_resource.xml')
            return stl(handler, namespace)
        else:
            handler_class = get_object_class(type)
            return handler_class.new_instance_form()


    new_resource__access__ = 'is_allowed_to_add'
    def new_resource(self, context):
        class_id = context.get_form_value('class_id')
        name = context.get_form_value('name')
        title = context.get_form_value('dc:title')

        # Empty name?
        name = name.strip() or title.strip()
        if not name:
            message = u'The name must be entered'
            return context.come_back(message)

        # Invalid name?
        name = checkid(name)
        if name is None:
            message = (u'The document name contains illegal characters,'
                       u' choose another one.')
            return context.come_back(message)

        # Find out the handler class
        handler_class = get_object_class(class_id)

        # Find out the name
        name = FileName.encode((name, handler_class.class_extension,
                                context.get_form_value('dc:language')))
        # Name already used?
        if self.has_handler(name):
            message = u'There is already another object with this name.'
            return context.come_back(message)

        # Build the handler
        handler = handler_class.new_instance()

        # Add the handler
        self.set_handler(name, handler)
        handler = self.get_handler(name)
        # Set the language
        language = context.get_form_value('dc:language')
        if language is None:
            root = self.get_site_root()
            languages = root.get_property('ikaaro:website_languages')
            language = languages[0]
        else:
            handler.set_property('dc:language', language)
        # Set the title
        handler.set_property('dc:title', title, language)

        # Come back
        if context.has_form_value('add_and_return'):
            goto = ';browse_content'
        else:
            handler = self.get_handler(name)
            goto = './%s/;%s' % (name, handler.get_firstview())

        message = u'New resource added.'
        return context.come_back(message, goto=goto)


    browse_dir__access__ = 'is_authenticated'
    def browse_dir(self, context):
        namespace = {}
        namespace['bc'] = widgets.Breadcrumb(filter_type=File.File, start=self)

        # Avoid general template
        response = context.response
        response.set_header('Content-Type', 'text/html; charset=UTF-8')

        handler = self.get_handler('/ui/Folder_browsedir.xml')
        return stl(handler, namespace)


    #######################################################################
    # Add / Upload File
    upload_file__access__ = 'is_allowed_to_add'
    def upload_file(self, context):
        file = context.get_form_value('file')
        if file is None:
            return context.come_back(u'The file must be entered')

        # Build a memory resource
        name, mimetype, body = file

        # Guess the language if it is not included in the filename
        if mimetype.startswith('text/'):
            short_name, type, language = FileName.decode(name)
            if language is None:
                # Guess the language
                encoding = Text.guess_encoding(body)
                data = unicode(body, encoding)
                language = i18n.oracle.guess_language(data)
                # Rebuild the name
                name = FileName.encode((short_name, type, language))

        # Invalid name?
        name = checkid(name)
        if name is None:
            return context.come_back(
                u'The document name contains illegal characters,'
                u' choose another one.')

        # Name already used?
        if self.has_handler(name):
            message = u'There is already another resource with this name.'
            return context.come_back(message)

        # Set the handler
        handler_class = get_object_class(mimetype)
        handler = handler_class()
        handler.load_state_from_string(body)
        self.set_handler(name, handler, format=mimetype)
        handler = self.get_handler(name)

        # Come back
        if context.has_form_value('add_and_return'):
            goto = ';browse_content'
        else:
            goto='./%s/;%s' % (name, handler.get_firstview())

        message = u'File uploaded.'
        return context.come_back(message, goto=goto)


    #######################################################################
    # Search
    def get_search_criteria(self):
        """Return the criteria as a list of dictionnary
        like [{'id': criteria_id, 'title' : criteria_title},...]
        """
        return self.search_criteria


register_object_class(Folder)
register_object_class(Folder, format="application/x-not-regular-file")
