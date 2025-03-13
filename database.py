from enum import IntEnum
from binary import BinaryFile
import os

# field type enum
class FieldType(IntEnum):
    INTEGER = 1
    STRING = 2

# Entry type alias
Entry = dict[str, int | str]

# type alias for table signature
TableSignature = list[tuple[str, FieldType]]

#TODO: add constants system for clearer code
#TODO: review code, specially the expanding of the string buffers

# database class
class Database:
    def __init__(self, name: str):
        self.name = name
        self.tables: dict[str, list[tuple[str, FieldType]]] = {}
        # table name -> field name -> value int or str -> list of entry positions
        self.indexes: dict[str, dict[str, dict[int | str, list[int]]]] = {}
        self.indexes_built = False
        self.indexes_built_tables = []
        self.open_files: dict[str, BinaryFile] = {}
        self.string_lookup_built = False
        self.string_lookup: dict[str, int] = {}
   
    # HELPER FUNCTIONS
    def _initialize_string_buffer(self, binary_file: BinaryFile, offset: int) -> None:
        """
            Initializes the string buffer:
            - Initializes a 16-byte buffer with zeros
        """
        binary_file.goto(offset)
        # initialize 16 bytes with zeros
        for _ in range(16):
            binary_file.write_integer(0, 1)
        binary_file.goto(0)

    def _initialize_entry_buffer(self, binary_file: BinaryFile, offset: int) -> None:
        """
            Initializes the entry buffer with 20-byte entry header:
            - Last used ID (4 bytes): 0
            - Number of entries (4 bytes): 0
            - First entry pointer (4 bytes): -1
            - Last entry pointer (4 bytes): -1
            - Reserved pointer (4 bytes): -1
        """
        binary_file.goto(offset)
        # last used ID - 4 bytes
        binary_file.write_integer(0, 4)  
        # number of entries - 4 bytes
        binary_file.write_integer(0, 4)  
        # pointer to first entry - 4 bytes
        binary_file.write_integer(-1, 4)
        # pointer to last entry - 4 bytes
        binary_file.write_integer(-1, 4)
        # reserved pointer - 4 bytes
        binary_file.write_integer(-1, 4)
        # go to start of file
        binary_file.goto(0)
        
    def _write_header(self, binary_file: BinaryFile, fields: list[tuple[str, FieldType]]) -> tuple[int, int]:
        """
            Writes the complete header section:
            - Magic constant "ULDB" (4 bytes)
            - Number of fields (4 bytes)
            - Table signature (variable size)
            - String buffer offset (4 bytes)
            - First available string buffer position (4 bytes)
            - First entry offset (4 bytes)
            
            :param binary_file: The binary file to write to
            :param fields: List of field tuples (name, type)
            :return: tuple of string buffer offset and entry buffer offset
        """
        # magic constant - raw bytes - not length-prefixed
        for b in "ULDB".encode('ascii'):
            binary_file.write_integer(b, 1)
        # number of fields
        binary_file.write_integer(len(fields), 4)
        # table signature
        for field_name, field_type in fields:
            # field type - 1 byte
            binary_file.write_integer(field_type.value, 1)
            # field name - length-prefixed UTF-8 string
            binary_file.write_string(field_name)
        # fixed offsets for string buffer and entry buffer
        string_buffer_offset = 64
        entry_buffer_offset = 80
        # string buffer offset
        binary_file.write_integer(string_buffer_offset, 4)
        # first available position in string buffer
        binary_file.write_integer(string_buffer_offset, 4)
        # entry buffer offset
        binary_file.write_integer(entry_buffer_offset, 4)
        # return offsets
        binary_file.goto(0)
        return string_buffer_offset, entry_buffer_offset

    def _parse_header(self, binary_file: BinaryFile) -> dict:
        """
            Parses the header of the table.
            :param binary_file: binary file
            :return: dict of offsets
            :raises ValueError: if magic constant is invalid
        """
        # go to start of file
        binary_file.goto(0)
        # magic constant
        magic_c = bytearray(4)
        for _ in range(4):
            magic_c.append(binary_file.read_integer(1))
        magic_c = magic_c.decode().strip('\x00')
        if magic_c != "ULDB":
            raise ValueError("Wrong type of file")
        # number of fields
        nfields = binary_file.read_integer(4)
        # table signature
        table_signature = []
        for _ in range(nfields):
            field_type = binary_file.read_integer(1)
            field_name = binary_file.read_string()
            table_signature.append((field_name, FieldType(field_type)))
        # offsets
        header = {}
        header['string_buffer_offset'] = binary_file.read_integer(4)
        header['string_buffer_first_available_position'] = binary_file.read_integer(4)
        header['entry_buffer_offset'] = binary_file.read_integer(4)
        header['signature'] = table_signature
        header['nfields'] = nfields
        header['magic_c'] = magic_c
        # go to start of file
        binary_file.goto(0)
        return header

    def _parse_entry_header(self, binary_file: BinaryFile, header: dict) -> dict:
        """
            Parses the mini header of the table.
            :param binary_file: binary file
            :param header: header of the table
            :return: dict of mini header
        """
        # goto entry buffer  
        binary_file.goto(header['entry_buffer_offset'])
        entry_header = {}
        # last used ID
        entry_header['last_used_id'] = binary_file.read_integer(4)
        # number of entries
        entry_header['nentries'] = binary_file.read_integer(4)
        # first entry pointer
        entry_header['first_entry_pointer'] = binary_file.read_integer(4)
        # last entry pointer
        entry_header['last_entry_pointer'] = binary_file.read_integer(4)
        # reserved pointer
        entry_header['reserved_pointer'] = binary_file.read_integer(4)
        # go to start of file
        binary_file.goto(0)
        return entry_header

    def _build_string_lookup(self, binary_file: BinaryFile, header: dict) -> None:
        """
            Builds a lookup table for the strings in the string buffer.
            :param binary_file: binary file
            :param header: header of the table
            :raises ValueError: if string buffer is corrupted
        """
        try:
            # initialize necessary variables for traverse of string buffer
            start = header['string_buffer_offset']
            end = header['string_buffer_first_available_position']
            # go to start of string buffer
            binary_file.goto(start)            
            # traverse string buffer
            while start < end:
                # len related errors are handled in read_string
                # read string
                try:
                    string = binary_file.read_string()
                    # add string and its offset to lookup table
                    self.string_lookup[string] = start
                except Exception as e:
                    # likely corrupted
                    raise ValueError(f"Corrupted string at position {start}: {e}")
                # update offset to next string
                start = binary_file._get_current_pos()
            self.string_lookup_built = True
        except Exception as e:
            raise IOError(f"Error while building string lookup: {e}")

    def _build_table_index(self, binary_file: BinaryFile, table_name: str) -> None:
        """
            Builds an index for the table.
            :param binary_file: binary file
            :param table_name: name of the table
        """
        # Initialisation of index for this table
        # TODO: maybe no need since init has self.indexes = {}
        if not hasattr(self, 'indexes'):
            self.indexes = {}
        # initialize index for this table
        if table_name not in self.indexes:
            self.indexes[table_name] = {}
        for field in self.tables[table_name]:
            self.indexes[table_name][field] = {}
        # read header and entry header
        binary_file.goto(0)
        header = self._parse_header(binary_file)
        entry_header = self._parse_entry_header(binary_file, header)
        # build string lookup
        self._build_string_lookup(binary_file, header)
        # go to start of entry buffer
        binary_file.goto(header['entry_buffer_offset'])
        # traverse valid entries
        current_pos = entry_header['first_entry_pointer']
        while current_pos != -1:  # -1 means end of linked list
            binary_file.goto(current_pos)
            # read entry id
            entry_id = binary_file.read_integer(4)
            # read entry fields
            entry_fields = {}
            for field_name, field_type in header['signature']:
                if field_type == FieldType.INTEGER:
                    value = binary_file.read_integer(4)
                elif field_type == FieldType.STRING:
                    string_pointer = binary_file.read_integer(4)
                    value = self.string_lookup.get(string_pointer, None)  # get string via lookup
                entry_fields[field_name] = value
            # add entry to index
            self.indexes[table_name][entry_id] = entry_fields
            # go to next entry
            current_pos = binary_file.read_integer(4)  # read next pointer
        # update indexes_built_tables
        self.indexes_built_tables.append(table_name)
        # update indexes_built flag
        self.indexes_built = True

    def _validate_add_entry_args(self, table_name: str, entry: Entry) -> bool:
        """
            Validates the arguments for the add_entry method.
            :param table_name: name of the table
            :param entry: dict[str, Field] to be added to the table
        """
        # check table name
        if table_name not in self.tables:
            raise ValueError(f"Table {table_name} does not exist")
        # check entry
        if not isinstance(entry, dict):
            raise TypeError(f"Entry must be a dictionary, got {type(entry)}")
        # check entry fields
        for fieldname, fieldvalue in entry.items():
            # check field name
            if not isinstance(fieldname, str):
                raise TypeError(f"Field name must be a string, got {type(fieldname)}")
            # check field exists in signature
            if fieldname not in [field[0] for field in self.tables[table_name]]:
                raise ValueError(f"Field {fieldname} does not exist in table {table_name}")
            # check field value
            if not isinstance(fieldvalue, int | str):
                raise TypeError(f"Field value must be an int or str, got {type(fieldvalue)}")
        return True
    
    def _add_string_to_buffer(self, binary_file: BinaryFile, string: str, table_name: str) -> int:
        """
            Adds a string to the string buffer.
            If the string already exists in the buffer, returns its position.
            If there's not enough space, expands the buffer.
            
            :param binary_file: binary file
            :param string: string to be added
            :param table_name: name of the table
            :return: position of the string in the buffer
            :raises ValueError: if string buffer is full and cannot be expanded
        """
        # if string already exists in the buffer
        if string in self.string_lookup:
            return self.string_lookup[string]
        # current position in file
        current_pos = binary_file._get_current_pos()
        # header information
        binary_file.goto(0)
        header = self._parse_header(binary_file)
        # required space for the string
        string_bytes = string.encode('utf-8')
        required_space = len(string_bytes) + 2  # 2 bytes for length prefix
        # available space in the buffer
        available_space = header['entry_buffer_offset'] - header['string_buffer_first_available_position']    
        if required_space > available_space:
            # not enough space -> expand the string buffer
            header, binary_file = self._expand_string_buffer(binary_file, header, table_name)
            # check expansion worked
            available_space = header['entry_buffer_offset'] - header['string_buffer_first_available_position']
            # if still not enough space
            if required_space > available_space:
                raise ValueError(f"String buffer full. Cannot add string of length {len(string_bytes)} bytes even after expansion.")
        # add string to buffer
        string_pos = header['string_buffer_first_available_position']
        binary_file.goto(string_pos)
        binary_file.write_string(string)
        # update first available position in header
        new_first_available_position = string_pos + required_space
        # find the correct position for the first available position in the header
        binary_file.goto(0)
        # skip magic constant (4 bytes)
        binary_file.goto(4)
        # read number of fields
        nfields = binary_file.read_integer(4)
        # skip field definitions
        for _ in range(nfields):
            field_type = binary_file.read_integer(1)
            field_name_len = binary_file.read_integer(2)
            binary_file.goto(binary_file._get_current_pos() + field_name_len)
        # skip string buffer offset (4 bytes)
        binary_file.goto(binary_file._get_current_pos() + 4)
        # write first available position
        binary_file.write_integer(new_first_available_position, 4)
        # update string lookup
        self.string_lookup[string] = string_pos
        # restore original position
        binary_file.goto(current_pos)
        return string_pos

    def _expand_string_buffer(self, binary_file: BinaryFile, header: dict, table_name: str) -> tuple[dict, BinaryFile]:
        """
            Expands the string buffer to double its current size.
            Uses the table index to rebuild the file instead of reading entries directly.
            
            :param binary_file: binary file
            :param header: header of the table
            :param table_name: name of the table
            :return: updated header
        """
        # current and new size
        curr_size = header['string_buffer_first_available_position'] - header['string_buffer_offset']
        if curr_size <= 0:
            curr_size = 16
        # TODO: come up with a better way to do this
        new_size = curr_size * 4 # arbitrary size (always a power of 2)
        # build index if not built
        if table_name not in self.indexes_built_tables:
            self._build_table_index(binary_file, table_name)
        # create temporary file
        temp_file_path = f"{self.name}/temp_{table_name}.table"
        with open(temp_file_path, "wb+") as temp_f:
            temp_binary = BinaryFile(temp_f)            
            # copy header to temp file and update offsets later
            binary_file.goto(0)
            for i in range(header['string_buffer_offset']):
                try:
                    byte_val = binary_file.read_integer(1)
                    temp_binary.write_integer(byte_val, 1)
                except Exception as e:
                    raise IOError(f"Error copying header byte {i}: {e}")
            # create new string buffer with expanded size
            new_string_buffer_offset = header['string_buffer_offset']
            new_entry_buffer_offset = new_string_buffer_offset + new_size
            # initialize the string buffer area with zeros
            temp_binary.goto(new_string_buffer_offset)
            for _ in range(new_size):
                temp_binary.write_integer(0, 1)
            # write at least 1 byte to be able to jump to entry buffer
            temp_binary.goto(new_entry_buffer_offset)
            temp_binary.write_integer(0, 1)
            # map of old string positions to new positions
            string_position_map = {}
            current_pos = header['string_buffer_offset']
            new_pos = new_string_buffer_offset
            # traverse valid strings in original file
            while current_pos < header['string_buffer_first_available_position']:
                try:
                    binary_file.goto(current_pos)
                    # read string length
                    str_len = binary_file.read_integer(2)
                    # record mapping of old position to new position
                    string_position_map[current_pos] = new_pos
                    # copy string to new buffer
                    binary_file.goto(current_pos)
                    # read the string manually to avoid issues with read_string
                    temp_binary.goto(new_pos)
                    temp_binary.write_integer(str_len, 2)  # write length
                    # copy the string bytes directly
                    binary_file.goto(current_pos + 2)  # skip length bytes
                    for i in range(str_len):
                        try:
                            byte_val = binary_file.read_integer(1)
                            temp_binary.write_integer(byte_val, 1)
                        except Exception as e:
                            raise IOError(f"Error copying string byte {i}: {e}")
                            # fill the rest with zeros
                            for j in range(i, str_len):
                                temp_binary.write_integer(0, 1)
                            break
                    # TODO: remove this
                    # for debugging, try to read the string
                    try:
                        binary_file.goto(current_pos)
                        string = binary_file.read_string()
                    except Exception as e:
                        raise IOError(f"Error reading string at pos {current_pos}: {e}")
                    # update positions
                    current_pos += 2 + str_len  # 2 bytes for length + string bytes
                    new_pos += 2 + str_len
                except Exception as e:
                    raise IOError(f"Error processing string at pos {current_pos}: {e}")
            # update first available position in string buffer
            new_first_available_position = new_pos
            # ensure new_first_available_position is not greater than new_entry_buffer_offset
            if new_first_available_position > new_entry_buffer_offset:
                new_first_available_position = new_string_buffer_offset + 16  # reset to initial position + 16 bytes
            # get entry header information
            try:
                entry_header = self._parse_entry_header(binary_file, header)
            except Exception as e:
                raise IOError(f"Error reading entry header: {e}")
            # create a default entry header
                entry_header = {
                    'last_used_id': 0,
                    'nentries': 0,
                    'first_entry_pointer': -1,
                    'last_entry_pointer': -1,
                    'reserved_pointer': -1
                }
            # get all entries from the index, sorted by ID
            entries = []
            for entry_id, entry_data in self.indexes[table_name].items():
                if isinstance(entry_id, int):  # skip field-specific indexes
                    entries.append((entry_id, entry_data))
            # sort entries by ID to maintain original order
            entries.sort(key=lambda x: x[0])
            # calculate entry size: ID + fields + prev/next pointers
            entry_size = 4 + len(header['signature']) * 4 + 8  
            # initialize temp file pointers
            prev_entry_pos = -1
            first_entry_pos = -1
            last_entry_pos = -1
            # write entry buffer header first
            temp_binary.goto(new_entry_buffer_offset)
            temp_binary.write_integer(entry_header['last_used_id'], 4)  # last used ID
            temp_binary.write_integer(len(entries), 4)  # number of entries
            # prep pointers
            first_entry_pointer_pos = temp_binary.file.tell()
            temp_binary.write_integer(-1, 4)  # first entry pointer (placeholder)
            last_entry_pointer_pos = temp_binary.file.tell()
            temp_binary.write_integer(-1, 4)  # last entry pointer (placeholder)
            temp_binary.write_integer(entry_header['reserved_pointer'], 4)  # reserved pointer
            # write entries
            for i, (entry_id, entry_data) in enumerate(entries):
                try:
                    # calculate new position
                    new_entry_pos = new_entry_buffer_offset + 20 + i * entry_size
                    # save first and last entry positions
                    if i == 0:
                        first_entry_pos = new_entry_pos
                    last_entry_pos = new_entry_pos
                    # write entry ID and fields
                    temp_binary.goto(new_entry_pos)
                    temp_binary.write_integer(entry_id, 4)
                    for field_name, field_type in header['signature']:
                        if field_type == FieldType.INTEGER:
                            temp_binary.write_integer(entry_data[field_name], 4)
                        elif field_type == FieldType.STRING:
                            # get string position from lookup
                            string_value = entry_data[field_name]
                            old_string_pos = self.string_lookup[string_value]
                            # update string pointer using string_position_map
                            new_string_pos = string_position_map[old_string_pos]
                            temp_binary.write_integer(new_string_pos, 4)
                    # write previous pointer
                    if prev_entry_pos == -1:
                        temp_binary.write_integer(-1, 4)  # first entry
                    else:
                        temp_binary.write_integer(prev_entry_pos, 4)
                    # write next pointer
                    if i == len(entries) - 1:
                        temp_binary.write_integer(-1, 4)  # last entry
                    else:
                        next_entry_pos = new_entry_buffer_offset + 20 + (i + 1) * entry_size
                        temp_binary.write_integer(next_entry_pos, 4)
                    prev_entry_pos = new_entry_pos
                except Exception as e:
                    raise IOError(f"Error writing entry {entry_id}: {e}")
            # update first and last entry pointers in header
            if len(entries) > 0:
                temp_binary.goto(first_entry_pointer_pos)
                temp_binary.write_integer(first_entry_pos, 4)
                temp_binary.goto(last_entry_pointer_pos)
                temp_binary.write_integer(last_entry_pos, 4)
            # find the correct position for the header offsets
            # we need to find where in the header these values are stored
            temp_binary.goto(0)
            # skip magic constant (4 bytes)
            temp_binary.goto(4)
            # read number of fields
            nfields = temp_binary.read_integer(4)
            # skip field definitions
            for _ in range(nfields):
                field_type = temp_binary.read_integer(1)
                field_name_len = temp_binary.read_integer(2)
                temp_binary.goto(temp_binary.file.tell() + field_name_len)
            # now we should be at the position of the string buffer offset
            offset_pos = temp_binary.file.tell()
            # update header offsets in temp file
            temp_binary.goto(offset_pos)
            temp_binary.write_integer(new_string_buffer_offset, 4)  # update string buffer offset
            temp_binary.write_integer(new_first_available_position, 4)  # update first available position
            temp_binary.write_integer(new_entry_buffer_offset, 4)  # update entry buffer offset
        # replace original file with temp file
        binary_file.file.close()
        import os
        import shutil
        os.remove(f"{self.name}/{table_name}.table")
        shutil.move(temp_file_path, f"{self.name}/{table_name}.table")
        # reopen the file
        f = open(f"{self.name}/{table_name}.table", "rb+")
        binary_file.__init__(f)        
        # create a new header dictionary with the correct values
        new_header = {
            'string_buffer_offset': new_string_buffer_offset,
            'string_buffer_first_available_position': new_first_available_position,
            'entry_buffer_offset': new_entry_buffer_offset,
            'signature': header['signature'],
            'nfields': header['nfields'],
            'magic_c': header['magic_c']
        }
        # rebuild string lookup with the correct header values
        self.string_lookup = {}
        self._build_string_lookup(binary_file, new_header)
        return new_header, binary_file

    # TABLE MANAGEMENT FUNCTIONS
    def list_tables(self) -> list[str]:
        """
            Lists all tables in the database.
            :return: list of table names
        """
        return list(self.tables.keys())

    def create_table(self, table_name: str, *fields: TableSignature) -> None:
        """
            Creates a new table with the given name and fields.
            :param table_name: name of the table
            :param fields: fields of the table
            :raises ValueError: if table name already exists
            :raises TypeError: if table name is not a string, fields is not a list, or fields is not a list of tuples (name, type)
        """
        # check table name
        if not isinstance(table_name, str):
            raise TypeError("Table name must be a string")
        # check fields
        if len(fields) == 0:
            raise ValueError("No fields provided")
        # check each field
        for field in fields:
            # check if it's a tuple
            if not isinstance(field, tuple):
                raise TypeError(f"Field must be a tuple, got {type(field)}")
            # check if tuple has exactly 2 elements
            if len(field) != 2:
                raise TypeError(f"Field must be a tuple of (name, type), got {len(field)} elements")
            # unpack and check types
            name, field_type = field
            if not isinstance(name, str):
                raise TypeError(f"Field name must be a string, got {type(name)}")
            if not isinstance(field_type, FieldType):
                raise TypeError(f"Field type must be FieldType, got {type(field_type)}")
        # check table name
        if table_name in self.tables:
            raise ValueError(f"Table {table_name} already exists")
        # update tables
        field_list = list(fields)
        self.tables[table_name] = field_list
        table_path = f"{self.name}/{table_name}.table"
        # Ensure database directory exists
        # TODO; create directory at init ?
        if not os.path.exists(self.name):
            os.makedirs(self.name)
        # write table
        with open(table_path, "wb+") as f:
            binary_file = BinaryFile(f)                    
            # write header and get offsets
            string_buffer_offset, entry_buffer_offset = self._write_header(binary_file, field_list)
            # initialize string buffer (16 bytes of zeros)
            self._initialize_string_buffer(binary_file, string_buffer_offset)           
            # initialize entry buffer
            self._initialize_entry_buffer(binary_file, entry_buffer_offset)
            # build table index
            self._build_table_index(binary_file, table_name)

    def delete_table(self, table_name: str) -> None:
        """
            Deletes the table of the given name.
            :param table_name: name of the table
            :raises ValueError: if table name does not exist
        """
        table_path = f"{self.name}/{table_name}.table"
        if not os.path.exists(table_path):
            # TODO: raise error or return ?
            raise ValueError(f"Table {table_name} does not exist")
        # remove table from tables
        os.remove(table_path)
        if table_name in self.tables:
            # remove table from tables
            self.tables.pop(table_name)            
        # remove table from indexes
        if table_name in self.indexes:
            self.indexes.pop(table_name)
        # remove table from indexes_built_tables
        if table_name in self.indexes_built_tables:
            self.indexes_built_tables.remove(table_name)
        # remove table from open_files
        # TODO: not yet implemented open_files, 
        #still considering if we should keep some tables open
        # if table_name in self.open_files:
        #     self.open_files.pop(table_name)

    def get_table_signature(self, table_name: str) -> TableSignature:
        """
            Returns the signature of the table of the given name.
            :param table_name: name of the table
            :return: signature of the table
            :raises ValueError: if table name does not exist
        """
        if table_name not in self.tables:
            raise ValueError(f"Table {table_name} does not exist")
        return self.tables[table_name]

    def add_entry(self, table_name: str, entry: Entry) -> None:
        """
            Adds an entry to the table of the given name.
            :param table_name: name of the table
            :param entry: entry to be added
            :raises ValueError: if table name does not exist
            :raises TypeError: if entry is not a dictionary
        """
        # arg validation
        self._validate_add_entry_args(table_name, entry)
        # get table signature
        signature = self.tables[table_name]
        # open table file
        with open(f"{self.name}/{table_name}.table", "rb+") as f:
            binary_file = BinaryFile(f)
            # read header and entry header
            header = self._parse_header(binary_file)
            entry_header = self._parse_entry_header(binary_file, header)
            # build string lookup if not already built
            if not self.string_lookup_built:
                self._build_string_lookup(binary_file, header)
            # generate unique ID for new entry
            new_id = entry_header['last_used_id'] + 1
            # calculate entry size: ID (4 bytes) + field values (4 bytes each) + prev/next pointers (8 bytes)
            entry_size = 4 + len(signature) * 4 + 8
            # new entry position: add at the end for now
            # TODO: reuse of deleted entries - use reserved_pointer 
            new_position = entry_header['last_entry_pointer']
            if new_position == -1:
                new_position = header['entry_buffer_offset'] + 20  # 20 bytes for entry header
            else:
                # if not empty add after the last one
                new_position = entry_header['last_entry_pointer'] + entry_size
            # write new entry to file
            binary_file.goto(new_position)
            # write entry ID
            binary_file.write_integer(new_id, 4)
            # write field values
            for field_name, field_type in signature:
                if field_type == FieldType.INTEGER:
                    binary_file.write_integer(entry[field_name], 4)
                elif field_type == FieldType.STRING:
                    # add string to buffer and get its position
                    string_position = self._add_string_to_buffer(binary_file, entry[field_name], table_name)
                    binary_file.write_integer(string_position, 4)
            # write previous pointer
            if entry_header['nentries'] > 0:
                # point to the previous last entry
                binary_file.write_integer(entry_header['last_entry_pointer'], 4)
            else:
                # if empty, point to -1
                binary_file.write_integer(-1, 4)
            # write next pointer: 
            # TODO: if reserved_pointer used, next should point to correct position
            binary_file.write_integer(-1, 4)
            # if not empty update the previous last entry's next pointer
            if entry_header['nentries'] > 0:
                # goto pos of next pointer in previous last entry
                binary_file.goto(entry_header['last_entry_pointer'] + entry_size - 4)  
                binary_file.write_integer(new_position, 4)

            # update entry header
            binary_file.goto(header['entry_buffer_offset'])
            # update last used ID
            binary_file.write_integer(new_id, 4)
            # update number of entries
            binary_file.write_integer(entry_header['nentries'] + 1, 4)
            # update first entry pointer if this is the first entry
            if entry_header['nentries'] == 0:
                binary_file.write_integer(new_position, 4)
            else:
                # skip first entry pointer, keep it as is
                binary_file.goto(header['entry_buffer_offset'] + 8)
            # update last entry pointer
            binary_file.write_integer(new_position, 4)
            # update index if it exists
            if table_name in self.indexes:
                # create entry with ID
                indexed_entry = entry.copy()
                indexed_entry['id'] = new_id
                # add to index
                self.indexes[table_name][new_id] = indexed_entry
                # add to field-specific indexes
                for field_name, value in entry.items():
                    if field_name not in self.indexes[table_name]:
                        self.indexes[table_name][field_name] = {}
                    if value not in self.indexes[table_name][field_name]:
                        self.indexes[table_name][field_name][value] = []
                    self.indexes[table_name][field_name][value].append(new_id)


if __name__ == "__main__":
    db = Database('programme')
    db.create_table(
        'cours',
        ('MNEMONIQUE', FieldType.INTEGER),
        ('NOM', FieldType.STRING),
        ('COORDINATEUR', FieldType.STRING),
        ('CREDITS', FieldType.INTEGER)
    )
    print("Created table:", db.list_tables())  # should show ['cours']
    
    # Test data
    test_data = [
        {'MNEMONIQUE': 101, 'NOM': 'Programmation',
         'COORDINATEUR': 'Thierry Massart', 'CREDITS': 10},
        {'MNEMONIQUE': 102, 'NOM': 'Fonctionnement des ordinateurs',
         'COORDINATEUR': 'Gilles Geeraerts', 'CREDITS': 5},
        {'MNEMONIQUE': 103, 'NOM': 'Algorithmique I',
         'COORDINATEUR': 'Olivier Markowitch', 'CREDITS': 10}
    ]

    # Add entries
    for entry in test_data:
        db.add_entry('cours', entry)

    # if db.indexes_built:
        # print("Indexes built:", db.indexes)
    # if db.string_lookup_built:
        # print("String lookup built:", db.string_lookup)
    
    # Removed cleanup to examine the file
    print("\nDatabase file created and populated successfully.")
    
    # Clean up
    # db.delete_table('cours')
    # print("\nCleaned up:", db.list_tables())  # should show []