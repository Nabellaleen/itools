# -*- coding: ISO-8859-1 -*-
# Copyright (C) 2003-2005 Juan David Ib��ez Palomar <jdavid@itaapy.com>
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# Import from itools
from File import File


class Text(File):

    class_mimetypes = ['text']
    class_extension = 'txt'


    #########################################################################
    # Load
    #########################################################################
    def _load_state(self, resource):
        state = self.state
        data = resource.read()
        state.encoding = self.guess_encoding(data)
        state.data = unicode(data, state.encoding)


    @staticmethod
    def guess_encoding(data):
        """
        Tries to guess the encoding by brute force. It is likely to get
        the wrong encoding, for example many utf8 files will be identified
        as latin1.
        """
        for encoding in ('ascii', 'utf8', 'iso8859'):
            try:
                unicode(data, encoding)
            except UnicodeError:
                pass
            else:
                return encoding

        # Default to UTF-8
        return 'utf8'


##    def guess_language(self):
##        """
##        XXX Now it does nothing, sometime in the future it will try to guess
##        the language of the data.
##        """


    #########################################################################
    # API
    #########################################################################
    def get_encoding(self):
        return self.state.encoding


    def to_str(self, encoding='UTF-8'):
        return self.state.data.encode(encoding)


File.register_handler_class(Text)
