# -*- coding: ISO-8859-1 -*-
# Copyright (C) 2003-2005 Juan David Ib��ez Palomar <jdavid@itaapy.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307  USA

# Import from itools
from itools.datatypes import Unicode
from itools.handlers import File
from itools.xml import XML
from itools.xhtml import XHTML
from itools.html.parser import Parser, DOCUMENT_TYPE, START_ELEMENT, \
     END_ELEMENT, ATTRIBUTE, COMMENT, TEXT



class Element(XHTML.Element):

    get_start_tag = XHTML.Element.get_start_tag_as_html


class InlineElement(Element, XHTML.InlineElement):
    pass


class BlockElement(Element, XHTML.BlockElement):
    pass


# XXX This class is almost identical to 'XHTML.Element'
class HeadElement(BlockElement):

    def to_str(self, encoding='UTF-8'):
        head = []
        head.append('<head>\n')
        head.append('    <meta http-equiv="Content-Type" content="text/html; charset=%s" />\n' % encoding)
        head.append(self.get_content(encoding))
        head.append('</head>')
        return ''.join(head)


elements_schema = {
    'a': {'type': InlineElement},
    'abbr': {'type': InlineElement},
    'acronym': {'type': InlineElement},
    'b': {'type': InlineElement},
    'cite': {'type': InlineElement},
    'code': {'type': InlineElement},
    'dfn': {'type': InlineElement},
    'em': {'type': InlineElement},
    'head': {'type': HeadElement},
    'kbd': {'type': InlineElement},
    'q': {'type': InlineElement},
    'samp': {'type': InlineElement},
    'span': {'type': InlineElement},
    'strong': {'type': InlineElement},
    'sub': {'type': InlineElement},
    'sup': {'type': InlineElement},
    'tt': {'type': InlineElement},
    'var': {'type': InlineElement},
    }


#############################################################################
# Documents
#############################################################################

class Document(XHTML.Document):
    """
    HTML files are a lot like XHTML, only the parsing and the output is
    different, so we inherit from XHTML instead of Text, even if the
    mime type is 'text/html'.

    The parsing is based on the HTMLParser class, which has a more object
    oriented approach than the expat parser used for xml, i.e. we inherit
    from HTMLParser.
    """

    class_mimetypes = ['text/html']
    class_extension = 'html'

    # HTML does not support XML namespace declarations
    ns_declarations = {}


    #########################################################################
    # The skeleton
    #########################################################################
    def get_skeleton(self, title=''):
        s = '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"\n' \
            '  "http://www.w3.org/TR/html4/loose.dtd">\n' \
            '<html>\n' \
            '  <head>\n' \
            '    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">\n' \
            '    <title>%(title)s</title>\n' \
            '  </head>\n' \
            '  <body></body>\n' \
            '</html>'
        return s % {'title': title}


    #######################################################################
    # Load/Save
    #######################################################################
    def _load_state(self, resource):
        state = self.state
        state.encoding = 'UTF-8'
        state.document_type = None
        state.children = []

        stack = []
        data = resource.read()
        parser = Parser()
        for event, value, line_number in parser.parse(data):
            if event == DOCUMENT_TYPE:
                state.document_type = value
            elif event == START_ELEMENT:
                schema = elements_schema.get(value, {'type': BlockElement})
                element_class = schema['type']
                stack.append(element_class(value))
            elif event == END_ELEMENT:
                element = stack.pop()

                # Detect <meta http-equiv="Content-Type" content="...">
                if element.name == 'meta':
                    if element.has_attribute(None, 'http-equiv'):
                        value = element.get_attribute(None, 'http-equiv')
                        if value == 'Content-Type':
                            continue

                if stack:
                    stack[-1].set_element(element)
                else:
                    state.children.append(element)
            elif event == ATTRIBUTE:
                name, value = value
                value = Unicode.decode(value, parser.encoding)
                stack[-1].set_attribute(None, name, value)
            elif event == COMMENT:
                comment = XML.Comment(value)
                if stack:
                    stack[-1].set_comment(comment)
                else:
                    state.children.append(comment)
            elif event == TEXT:
                if stack:
                    stack[-1].set_text(value, parser.encoding)
                else:
                    value = Unicode.decode(value, parser.encoding)
                    state.children.append(value)


    def to_str(self, encoding='UTF-8'):
        s = []
        # The declaration
        if self.state.document_type is not None:
            s.append('<!%s>' % self.state.document_type)
        # The children
        for child in self.state.children:
            if isinstance(child, unicode):
                s.append(child)
            else:
                s.append(child.to_str(encoding))
        return ''.join(s)


    #######################################################################
    # API
    #######################################################################
    def get_root_element(self):
        # XXX Probably this should work like XML
        for child in self.state.children:
            if isinstance(child, Element):
                return child


XHTML.Document.register_handler_class(Document)
