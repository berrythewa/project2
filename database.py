from enum import IntEnum
from binary import BinaryFile
import os
import shutil
# field type enum
class FieldType(IntEnum):
    INTEGER = 1
    STRING = 2

# field value type alias
Field = int | str

# Entry type alias
Entry = dict[str, Field]

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
        self.string_lookup_built = False
        self.string_lookup: dict[str, int] = {}
        # TODO: consider if necessary to keep open files
        # self.open_files: dict[str, BinaryFile] = {}
   
    # HELPER FUNCTIONS
    def _initialize_string_buffer(self, binary_file: BinaryFile, offset: int, string_buffer_size: int = 16) -> None:
        """
            Initializes the string buffer:
            - Initializes a 16-byte buffer with zeros
        """
        binary_file.goto(offset)
        # initialize 16 bytes with zeros
        for _ in range(string_buffer_size):
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
        
    def _write_header(self, binary_file: BinaryFile, fields: list[tuple[str, FieldType]], string_buffer_offset: int = 64, entry_buffer_offset: int = 80) -> tuple[int, int]:
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
        # string buffer offset
        binary_file.write_integer(string_buffer_offset, 4)
        # first available position in string buffer
        binary_file.write_integer(string_buffer_offset, 4)
        # entry buffer offset
        binary_file.write_integer(entry_buffer_offset, 4)
        # return to start of file
        # TODO: do we need to restore pointer to start of file?
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
        # initialize field-specific indexes using field names
        for field_name, field_type in self.tables[table_name]:
            self.indexes[table_name][field_name] = {}
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
            
            # Build field-specific indexes for this entry
            for field_name, value in entry_fields.items():
                if value not in self.indexes[table_name][field_name]:
                    self.indexes[table_name][field_name][value] = []
                self.indexes[table_name][field_name][value].append(entry_id)
                
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
            if not isinstance(fieldvalue, Field):
                raise TypeError(f"Field value must be an int or str, got {type(fieldvalue)}")
        return True
    
    def _add_string_to_buffer(self, binary_file: BinaryFile, string: str, table_name: str) -> tuple[int, dict, BinaryFile]:
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
        # TODO: since there is a good chance file will be expanded,
        # we should not rely on current position
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
            header, binary_file = self._expand_string_buffer(binary_file, header, 
                self._parse_entry_header(binary_file, header), 
                table_name
            )
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
        # binary_file.goto(4)
        for _ in range(4):
            binary_file.read_integer(1)
        # read number of fields
        nfields = binary_file.read_integer(4)
        # skip field definitions
        for _ in range(nfields):
            field_type = binary_file.read_integer(1)
            field_name_len = binary_file.read_integer(2)
            binary_file.goto(binary_file._get_current_pos() + field_name_len) 
        # skip string buffer offset (4 bytes)
        binary_file.read_integer(4)
        # write first available position
        binary_file.write_integer(new_first_available_position, 4)
        # update string lookup
        self.string_lookup[string] = string_pos
        # SILENCED tmp: restore original position
        # binary_file.goto(current_pos)
        return string_pos, header, binary_file

    def _expand_string_buffer(self, binary_file: BinaryFile, header: dict, entry_header: dict, table_name: str) -> tuple[dict, BinaryFile]:
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
        new_string_buffer_offset = header['string_buffer_offset']
        new_entry_buffer_offset = new_string_buffer_offset + new_size        
        with open(temp_file_path, "wb+") as temp_f:
            temp_binary = BinaryFile(temp_f)
            # write magic constant
            new_string_buffer_offset, new_entry_buffer_offset = self._write_header(temp_binary, 
                    self.tables[table_name], new_string_buffer_offset, new_entry_buffer_offset)
            # initialize buffers
            self._initialize_string_buffer(temp_binary, new_string_buffer_offset, new_size)
            self._initialize_entry_buffer(temp_binary, new_entry_buffer_offset)
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
                    # update positions
                    current_pos += 2 + str_len  # 2 bytes for length + string bytes
                    new_pos += 2 + str_len
                except Exception as e:
                    raise IOError(f"Error processing string at pos {current_pos}: {e}")
            # simply copy all entries to temp file from new entry buffer offset
            self._copy_entries(binary_file, temp_binary, new_entry_buffer_offset, string_position_map)
        # replace original file with temp file
        binary_file.file.close()
        os.remove(f"{self.name}/{table_name}.table")
        shutil.move(temp_file_path, f"{self.name}/{table_name}.table")
        # reopen the file
        f = open(f"{self.name}/{table_name}.table", "rb+")
        binary_file.__init__(f)
        # create a new header dictionary with the correct values
        new_header = self._parse_header(binary_file)
        # rebuild string lookup with the correct header values
        self.string_lookup = {}
        self._build_string_lookup(binary_file, new_header)
        return new_header, binary_file

    def _copy_entries(self, binary_file: BinaryFile, temp_binary: BinaryFile, new_entry_buffer_offset: int, string_position_map: dict[int, int]) -> None:
        """
            Copies all entries from the original file to the temp file.
            Also handles string pointers to new positions. Called after expanding the string buffer.
            
            :param binary_file: Original binary file
            :param temp_binary: Temporary binary file to write to
            :param new_entry_buffer_offset: New offset where entries should start in temp file
            :param string_position_map: Mapping of old string positions to new positions
        """
        # get entry header from original file
        header = self._parse_header(binary_file)
        entry_header = self._parse_entry_header(binary_file, header)        
        # if no entries -> write the entry header and return
        if entry_header['nentries'] == 0 or entry_header['first_entry_pointer'] == -1:
            temp_binary.goto(new_entry_buffer_offset)
            temp_binary.write_integer(entry_header['last_used_id'], 4)
            temp_binary.write_integer(0, 4)  # no entries
            temp_binary.write_integer(-1, 4)  # first entry pointer
            temp_binary.write_integer(-1, 4)  # last entry pointer
            temp_binary.write_integer(-1, 4)  # reserved pointer
            return
        # read all entries into memory
        entries = []
        entry_size = 4 + len(header['signature']) * 4 + 8  # ID + fields + prev/next pointers
        # traverse all entries in original file
        current_pos = entry_header['first_entry_pointer']
        visited_positions = set()  # Keep track of positions we've already visited
        max_entries = entry_header['nentries'] * 2  # Safety limit - should never need more than this
        entry_count = 0
        try:
            while current_pos != -1 and current_pos not in visited_positions and entry_count < max_entries:
                visited_positions.add(current_pos)
                entry_count += 1
                # check if position is valid
                if current_pos < 0 or current_pos >= binary_file.get_size():
                    print(f"Warning: Invalid entry position {current_pos}, breaking loop")
                    break
                # read entry data
                entry_data = {}
                entry_data['position'] = current_pos
                # read entry id
                binary_file.goto(current_pos)
                entry_data['id'] = binary_file.read_integer(4)
                # read field values
                entry_data['fields'] = []
                for field_name, field_type in header['signature']:
                    if field_type == FieldType.INTEGER:
                        value = binary_file.read_integer(4)
                        entry_data['fields'].append((field_name, field_type, value))
                    elif field_type == FieldType.STRING:
                        old_string_pos = binary_file.read_integer(4)
                        new_string_pos = string_position_map.get(old_string_pos, -1)
                        entry_data['fields'].append((field_name, field_type, new_string_pos))
                # read previous pointer
                entry_data['prev_pointer'] = binary_file.read_integer(4)
                # read next pointer
                next_ptr = binary_file.read_integer(4)
                entry_data['next_pointer'] = next_ptr
                # add entry to list
                entries.append(entry_data)
                # move to next entry
                current_pos = next_ptr
        except Exception as e:
            print(f"Error reading entries: {e}")
            # continue with retrieved entries so far
        # write the entry header to temp file
        temp_binary.goto(new_entry_buffer_offset)
        temp_binary.write_integer(entry_header['last_used_id'], 4)
        temp_binary.write_integer(len(entries), 4)  # number of entries we actually read
        # calculate new positions for entries
        first_entry_pos = new_entry_buffer_offset + 20  # 20 bytes for entry header
        # write entries to temp file
        prev_entry_pos = -1
        for i, entry_data in enumerate(entries):
            new_entry_pos = first_entry_pos + (i * entry_size)  
            # ensure new position is reachable in temp_binary
            temp_file_size = temp_binary.get_size()
            if new_entry_pos >= temp_file_size:
                # need to extend the temp file
                temp_binary.goto(temp_file_size)
                # write zeros to extend the file
                fill_size = new_entry_pos - temp_file_size
                for _ in range(fill_size):
                    temp_binary.write_integer(0, 1)            
            # write entry ID
            temp_binary.goto(new_entry_pos)
            temp_binary.write_integer(entry_data['id'], 4)
            # write field values
            for field_name, field_type, value in entry_data['fields']:
                temp_binary.write_integer(value, 4)
            # write previous pointer
            if i == 0:
                temp_binary.write_integer(-1, 4)  # first entry
            else:
                temp_binary.write_integer(prev_entry_pos, 4)
            # write next pointer
            if i == len(entries) - 1:
                temp_binary.write_integer(-1, 4)  # last entry
            else:
                next_entry_pos = new_entry_pos + entry_size
                temp_binary.write_integer(next_entry_pos, 4)
            # update prev_entry_pos for next iteration
            prev_entry_pos = new_entry_pos
        # update entry header pointers
        temp_binary.goto(new_entry_buffer_offset + 8)  # skip last_used_id and nentries
        if len(entries) > 0:
            temp_binary.write_integer(first_entry_pos, 4)  # first entry pointer
            last_entry_pos = first_entry_pos + ((len(entries) - 1) * entry_size)
            temp_binary.write_integer(last_entry_pos, 4)  # last entry pointer
        else:
            temp_binary.write_integer(-1, 4)  # first entry pointer
            temp_binary.write_integer(-1, 4)  # last entry pointer
        # write reserved pointer
        temp_binary.write_integer(entry_header['reserved_pointer'], 4)  # reserved pointer

    def _update_index(self, table_name: str, entry: Entry, entry_id: int) -> None:
        """
            Updates the index for the given table and entry.
            :param table_name: name of the table
            :param entry: entry to be added
            :param entry_id: id of the entry
        """ 
        # get table signature
        signature = self.tables[table_name]
        # build index if not already built
        if table_name not in self.indexes_built_tables:
            self._build_table_index(binary_file, table_name)
        # update index
        self.indexes[table_name][entry_id] = entry
        # update field-specific indexes
        for field_name, value in entry.items():
            if field_name not in self.indexes[table_name]:
                self.indexes[table_name][field_name] = {}
            if value not in self.indexes[table_name][field_name]:
                self.indexes[table_name][field_name][value] = []
            self.indexes[table_name][field_name][value].append(entry_id)


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
        # check database directory exists
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
            # check for new strings in entry and replace them with their string_buffer positions
            for field_name, field_value in entry.items():
                if isinstance(field_value, str):
                    string_pos, header, binary_file = self._add_string_to_buffer(binary_file, field_value, table_name)
                    entry[field_name] = string_pos
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
            # calculate new_position
            new_position = entry_header['last_entry_pointer']
            if new_position == -1:
                new_position = header['entry_buffer_offset'] + 20  # 20 bytes for entry header
            else:
                # if not empty add after the last one
                new_position = entry_header['last_entry_pointer'] + entry_size
            # ensure new position is reachable
            current_file_size = binary_file.get_size()
            if new_position >= current_file_size:
                # need to extend the file
                binary_file.goto(current_file_size)
                # write zeros to extend the file
                fill_size = new_position - current_file_size
                for _ in range(fill_size):
                    binary_file.write_integer(0, 1)
            # seek to new_position
            binary_file.goto(new_position)
            # write entry ID
            binary_file.write_integer(new_id, 4)
            # write field values
            for field_name, field_type in signature:
                # TODO: maybe no need to check type?
                binary_file.write_integer(entry[field_name], 4)
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
                prev_next_ptr_pos = entry_header['last_entry_pointer'] + entry_size - 4
                binary_file.goto(prev_next_ptr_pos)
                binary_file.write_integer(new_position, 4)
            # update entry header
            binary_file.goto(header['entry_buffer_offset'])
            # update last used ID
            binary_file.write_integer(new_id, 4)
            # update number of entries
            binary_file.write_integer(entry_header['nentries'] + 1, 4)
            # update first entry pointer if first entry
            if entry_header['nentries'] == 0:
                binary_file.write_integer(new_position, 4)
            else:
                # first entry pointer did not change
                first_entry_ptr = entry_header['first_entry_pointer']
                binary_file.write_integer(first_entry_ptr, 4)
            # update last entry pointer
            binary_file.write_integer(new_position, 4)
            # update index
            self._update_index(table_name, entry, new_id)

    # TODO: have a function handle opening/closing of file ?
    # might help with keeping some tables open
    def get_complete_table(self, table_name: str) -> list[Entry]:
        """
            Returns the complete table of the given name.
            :param table_name: name of the table
            :return: list of all entries in the table
            :raises ValueError: if table name does not exist
            :raises ValueError: if table is not registered
        """
        # check if table exists
        table_path = f"{self.name}/{table_name}.table"
        if not os.path.exists(table_path):
            raise ValueError(f"Table {table_name} does not exist")
        # consider adding a register table function
        if table_name not in self.tables:
            raise ValueError(f"Table {table_name} is not registered")
        # open table file
        with open(table_path, "rb+") as f:
            binary_file = BinaryFile(f)
            if table_name not in self.indexes_built_tables:
                self._build_table_index(binary_file, table_name)
            # read entries
            entries = []
            for entry_id, entry_data in self.indexes[table_name].items():
                if isinstance(entry_id, int):  # skip field-specific indexes
                    entries.append((entry_id, entry_data))
            # sort entries by ID to maintain original order
            entries.sort(key=lambda x: x[0])
            # return entries
            return entries
    
    def get_entry(self, table_name: str, field_name: str, field_value: Field) -> Entry | None:
        """
            Returns the entry of the given name and field value.
            :param table_name: name of the table
            :param field_name: name of the field
            :param field_value: value of the field
            :return: entry
            :raises ValueError: if table name does not exist
            :raises ValueError: if table is not registered
        """
        # check if table exists
        table_path = f"{self.name}/{table_name}.table"
        if not os.path.exists(table_path):
            raise ValueError(f"Table {table_name} does not exist")
        # check if table is registered
        if table_name not in self.tables:
            raise ValueError(f"Table {table_name} is not registered")
        # open table file
        entry = None
        with open(table_path, "rb+") as f:
            binary_file = BinaryFile(f)
            # build table index if not already built
            if table_name not in self.indexes_built_tables:
                self._build_table_index(binary_file, table_name)
            # get entry ID from field-specific index
            # TODO: get first occurence or last occurence ?
            entry_id = self.indexes[table_name][field_name][field_value][0]
            # get entry
            entry = self.indexes[table_name][entry_id]
        return entry

    def get_entries(self, table_name: str, field_name: str, field_value: Field) -> list[Entry]:
        """
            Returns the entries of the given table and field name and field value.
            :param table_name: name of the table
            :param field_name: name of the field
            :param field_value: value of the field
            :return: list of entries
        """
        # check if table exists
        table_path = f"{self.name}/{table_name}.table"
        if not os.path.exists(table_path):
            raise ValueError(f"Table {table_name} does not exist")
        # check if table is registered
        if table_name not in self.tables:
            raise ValueError(f"Table {table_name} is not registered")
        # open table file
        entries = []
        with open(table_path, "rb+") as f:
            binary_file = BinaryFile(f)
            # build table index if not already built
            if table_name not in self.indexes_built_tables:
                self._build_table_index(binary_file, table_name)
            # get entry IDs from field-specific index
            entry_ids = self.indexes[table_name][field_name][field_value]
            # get entries
            for entry_id in entry_ids:
                entries.append(self.indexes[table_name][entry_id])
        # return entries
        return entries

    def get_table_size(self, table_name: str) -> int:
        """
            Returns the size of the table of the given name.
            :param table_name: name of the table
            :return: size of the table
        """
        # check if table exists
        table_path = f"{self.name}/{table_name}.table"
        if not os.path.exists(table_path):
            raise ValueError(f"Table {table_name} does not exist")
        # check if table is registered
        if table_name not in self.tables:
            raise ValueError(f"Table {table_name} is not registered")
        # open table file
        table_size = 0
        with open(table_path, "rb+") as f:
            binary_file = BinaryFile(f)
            # get table size
            header = self._parse_header(binary_file)
            entry_header = self._parse_entry_header(binary_file, header)
            table_size = entry_header['nentries']
        # return table size
        return table_size
    
    def select_entry(self, table_name: str, fields: tuple[str], field_name: str, field_value: Field) -> Field | tuple[Field]:
        """
            Selects the fields of the entry of the given table where fieldname has fieldvalue.
            :param table_name: name of the table
            :param fields: fields to be selected
            :param field_name: name of the field
            :param field_value: value of the field
            :return: entry
        """
        # check if table exists
        table_path = f"{self.name}/{table_name}.table"
        if not os.path.exists(table_path):
            raise ValueError(f"Table {table_name} does not exist")
        # check if table is registered
        if table_name not in self.tables:
            raise ValueError(f"Table {table_name} is not registered")
        # select fields
        selected_fields = []
        # open table file
        with open(table_path, "rb+") as f:
            binary_file = BinaryFile(f)
            # build table index if not already built
            if table_name not in self.indexes_built_tables:
                self._build_table_index(binary_file, table_name)
            # get entry ID from field-specific index
            # TODO: get first occurence or last occurence ? need a logic for this
            entry_id = self.indexes[table_name][field_name][field_value][0]
            # get entry
            entry = self.indexes[table_name][entry_id]
            # select fields
            if len(fields) == 1:
                selected_fields.append(entry[fields[0]])
            else:
                for field in fields:
                    selected_fields.append(entry[field])
        # return only value if one field is selected
        return selected_fields if len(selected_fields) > 1 else selected_fields[0]

    def select_entries(self, table: str, fields: tuple[str], field_name: str, field_value: Field) -> list[Field | tuple[Field]]:
        """
            Selects the fields of the entries of the given table where fieldname has fieldvalue.
            :param table: name of the table
            :param fields: fields to be selected
            :param field_name: name of the field
            :param field_value: value of the field
            :return: list of entries
        """
        # check if table exists
        table_path = f"{self.name}/{table}.table"
        if not os.path.exists(table_path):
            raise ValueError(f"Table {table} does not exist")
        # check if table is registered
        if table not in self.tables:
            raise ValueError(f"Table {table} is not registered")
        # select entries
        selected_fields = []
        with open(table_path, "rb+") as f:
            binary_file = BinaryFile(f)
            # build table index if not already built
            if table not in self.indexes_built_tables:
                self._build_table_index(binary_file, table)
            # get entry IDs from field-specific index
            entry_ids = self.indexes[table][field_name][field_value]
            # get entries
            for entry_id in entry_ids:
                for field in fields:
                    selected_fields.append(self.indexes[table][entry_id][field])
        return selected_fields

# if __name__ == "__main__":
#     db = Database('programme')
#     db.create_table(
#         'cours',
#         ('MNEMONIQUE', FieldType.INTEGER),
#         ('NOM', FieldType.STRING),
#         ('COORDINATEUR', FieldType.STRING),
#         ('CREDITS', FieldType.INTEGER)
#     )
#     print("Created table:", db.list_tables())  # should show ['cours']
    
#     db.add_entry('cours', {
#         'MNEMONIQUE': 101, 
#         'NOM': 'Progra',
#         'COORDINATEUR': 'T. Massart', 
#         'CREDITS': 10
#         }) # ajout de Progra
#     db.add_entry('cours', {
#         'MNEMONIQUE': 102, 
#         'NOM': 'FDO',
#         'COORDINATEUR': 'G. Geeraerts', 
#         'CREDITS': 5
#         }) # ajout de FDO
#     db.add_entry('cours', {
#         'MNEMONIQUE': 103, 
#         'NOM': 'Algo 1',
#         'COORDINATEUR': 'O. Markowitch', 
#         'CREDITS': 10
#         }) # ajout d'Algo 1

#     print("\nTable size:", db.get_table_size('cours'))
    
#     print("\n--- Index Structure ---")
#     print("Entry ID indexes:")
#     for key in db.indexes['cours'].keys():
#         if isinstance(key, int):
#             print(f"  Entry ID {key}: {db.indexes['cours'][key]}")
    
#     print("\nField-specific indexes:")
#     for field_name, field_type in db.get_table_signature('cours'):
#         print(f"  Field '{field_name}':")
#         if field_name in db.indexes['cours']:
#             for value, entry_ids in db.indexes['cours'][field_name].items():
#                 print(f"    Value '{value}' -> Entry IDs: {entry_ids}")
#         else:
#             print("    Not indexed")
    
#     print("\n--- Query Results ---")
#     print("Complete table:", db.get_complete_table('cours'))
#     print("Entry with CREDITS=10:", db.get_entry('cours', 'CREDITS', 10))
#     print("Entries with CREDITS=10:", db.get_entries('cours', 'CREDITS', 10))
#     print("MNEMONIQUE values for CREDITS=10:", db.select_entries('cours', ('MNEMONIQUE',), 'CREDITS', 10))
#     print("(MNEMONIQUE, NOM) for CREDITS=10:", db.select_entries('cours', ('MNEMONIQUE', 'NOM'), 'CREDITS', 10))
#     print("(NOM, MNEMONIQUE) for CREDITS=10:", db.select_entries('cours', ('NOM', 'MNEMONIQUE'), 'CREDITS', 10))
    
#     # clean up
#     db.delete_table('cours')
#     print("\nCleaned up:", db.list_tables())  # should show []