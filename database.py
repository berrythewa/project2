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
   

    # TABLE INITIALIZATION HELPER FUNCTIONS
    def _initialize_string_buffer(self, binary_file: BinaryFile, offset: int) -> None:
        """
            Initializes the string buffer:
            - Writes a null terminator (0x00) at the given offset
        """
        track_pos = offset
        for _ in range(16):  # 16 bytes initial size
            binary_file.goto(track_pos)
            track_pos += binary_file.write_integer(0, 1)
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
        track_pos = offset
        binary_file.goto(track_pos)
        # last used ID
        track_pos += binary_file.write_integer(0, 4)  
        # number of entries
        binary_file.goto(track_pos)
        track_pos += binary_file.write_integer(0, 4)  
        
        # pointer to first entry
        binary_file.goto(track_pos)
        track_pos += binary_file.write_integer(-1, 4)
        # pointer to last entry
        binary_file.goto(track_pos)
        track_pos += binary_file.write_integer(-1, 4)
        # reserved pointer
        binary_file.goto(track_pos)
        track_pos += binary_file.write_integer(-1, 4)
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
        # 1. write magic constant as 4 raw bytes (not length-prefixed)
        for b in "ULDB".encode('ascii'):
            binary_file.write_integer(b, 1)
        # 2. write number of fields
        binary_file.write_integer(len(fields), 4)
        # 3. write table signature
        for field_name, field_type in fields:
            # Field type (1 byte)
            binary_file.write_integer(field_type.value, 1)
            # Field name (length-prefixed UTF-8 string)
            binary_file.write_string(field_name)
        # fixed offsets for string buffer and entry buffer
        string_buffer_offset = 64
        entry_buffer_offset = 80
        # 4. write string buffer offset
        binary_file.write_integer(string_buffer_offset, 4)
        # 5. write first available position in string buffer
        binary_file.write_integer(string_buffer_offset, 4)
        # 6. write entry buffer offset
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
        # read magic constant
        magic_c = bytearray(4)
        for _ in range(4):
            magic_c.append(binary_file.read_integer(1))
        magic_c = magic_c.decode().strip('\x00')
        print("Found magic constant:", magic_c)
        if magic_c != "ULDB":
            raise ValueError("Wrong type of file")
        # read number of fields
        nfields = binary_file.read_integer(4)
        # read table signature
        table_signature = []
        for _ in range(nfields):
            field_type = binary_file.read_integer(1)
            field_name = binary_file.read_string()
            table_signature.append((field_name, FieldType(field_type)))
        # read offsets
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
        # go to entry buffer  
        binary_file.goto(header['entry_buffer_offset'])
        entry_header = {}
        # read last used ID
        entry_header['last_used_id'] = binary_file.read_integer(4)
        # read number of entries
        entry_header['nentries'] = binary_file.read_integer(4)
        # read first entry pointer
        entry_header['first_entry_pointer'] = binary_file.read_integer(4)
        # read last entry pointer
        entry_header['last_entry_pointer'] = binary_file.read_integer(4)
        # read reserved pointer
        entry_header['reserved_pointer'] = binary_file.read_integer(4)
        # go to start of file
        binary_file.goto(0)
        return entry_header

    def _build_string_lookup(self, binary_file: BinaryFile, header: dict) -> None:
        """
            Builds a lookup table for the strings in the string buffer.
            :param binary_file: binary file
            :param header: header of the table
        """
        try:
            # initialize 
            start = header['string_buffer_offset']
            end = header['string_buffer_first_available_position']
            binary_file.goto(start)

            # read string buffer
            while start < end:
                # read length of string (2 bytes)
                read_len = binary_file.read_integer(2)
                
                # check if length is valid
                if start + read_len + 2 > end:
                    raise ValueError("String buffer corrupted: read length exceeds available space.")
                
                # read string
                string = binary_file.read_string(read_len)
                
                # add string and its offset to lookup table
                self.string_lookup[string] = start
                
                # update offset to next string
                start += read_len + 2
            self.string_lookup_built = True
        except Exception as e:
            print(f"Error while building string lookup: {e}")
            raise


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
            if fieldname not in self.tables[table_name]:
                raise ValueError(f"Field {fieldname} does not exist in table {table_name}")
            # check field value
            if not isinstance(fieldvalue, Field):
                raise TypeError(f"Field value must be a Field, got {type(fieldvalue)}")
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
        # Check if string already exists in the buffer
        if string in self.string_lookup:
            return self.string_lookup[string]
        
        # Get current position in file
        current_pos = binary_file.file.tell()
        
        # Get header information
        binary_file.goto(0)
        header = self._parse_header(binary_file)
        
        # Calculate required space for the string
        string_bytes = string.encode('utf-8')
        required_space = len(string_bytes) + 2  # 2 bytes for length prefix
        
        # Check if there's enough space in the buffer
        available_space = header['entry_buffer_offset'] - header['string_buffer_first_available_position']
        
        if required_space > available_space:
            # Not enough space - expand the string buffer
            header = self._expand_string_buffer(binary_file, header, table_name)
            
            # Verify we now have enough space
            available_space = header['entry_buffer_offset'] - header['string_buffer_first_available_position']
            if required_space > available_space:
                raise ValueError(f"String buffer full. Cannot add string of length {len(string_bytes)} bytes even after expansion.")
        
        # Add string to buffer
        string_pos = header['string_buffer_first_available_position']
        binary_file.goto(string_pos)
        binary_file.write_string(string)
        
        # Update first available position in header
        new_pos = string_pos + required_space
        binary_file.goto(header['string_buffer_offset'] - 4)  # Position of first available position in header
        binary_file.write_integer(new_pos, 4)
        
        # Update string lookup
        self.string_lookup[string] = string_pos
        
        # Restore original position
        binary_file.goto(current_pos)
        
        return string_pos

    def _expand_string_buffer(self, binary_file: BinaryFile, header: dict, table_name: str) -> dict:
        """
            Expands the string buffer to double its current size.
            :param binary_file: binary file
            :param header: header of the table
            :param table_name: name of the table
            :return: updated header
        """
        # Calculate current and new size
        curr_size = header['string_buffer_first_available_position'] - header['string_buffer_offset']
        new_size = curr_size * 2  # Double the size (always a power of 2)
        
        print(f"Expanding string buffer from {curr_size} to {new_size} bytes")
        
        # Create a temporary file
        temp_file_path = f"{self.name}/temp_{table_name}.table"
        with open(temp_file_path, "wb+") as temp_f:
            temp_binary = BinaryFile(temp_f)
            
            # 1. Copy header to temp file (we'll update offsets later)
            binary_file.goto(0)
            for i in range(header['string_buffer_offset']):
                byte_val = binary_file.read_integer(1)
                temp_binary.write_integer(byte_val, 1)
            
            # 2. Create new string buffer with expanded size
            new_string_buffer_offset = header['string_buffer_offset']
            new_entry_buffer_offset = new_string_buffer_offset + new_size
            
            # 3. Copy existing strings to new buffer
            binary_file.goto(header['string_buffer_offset'])
            temp_binary.goto(new_string_buffer_offset)
            
            # Map of old string positions to new positions
            string_position_map = {}
            current_pos = header['string_buffer_offset']
            new_pos = new_string_buffer_offset
            
            while current_pos < header['string_buffer_first_available_position']:
                binary_file.goto(current_pos)
                
                # Read string length
                str_len = binary_file.read_integer(2)
                
                # Record mapping of old position to new position
                string_position_map[current_pos] = new_pos
                
                # Copy string to new buffer
                binary_file.goto(current_pos)
                string = binary_file.read_string()
                temp_binary.goto(new_pos)
                temp_binary.write_string(string)
                
                # Update positions
                current_pos += 2 + str_len  # 2 bytes for length + string bytes
                new_pos += 2 + str_len
            
            # Update first available position in string buffer
            new_first_available_position = new_pos
            
            # 4. Copy entry buffer header
            binary_file.goto(header['entry_buffer_offset'])
            temp_binary.goto(new_entry_buffer_offset)
            
            # Read entry header
            entry_header = self._parse_entry_header(binary_file, header)
            
            # Calculate entry offset difference
            entry_offset_diff = new_entry_buffer_offset - header['entry_buffer_offset']
            
            # Write updated entry header
            temp_binary.write_integer(entry_header['last_used_id'], 4)  # Last used ID
            temp_binary.write_integer(entry_header['nentries'], 4)      # Number of entries
            
            # Update first entry pointer
            if entry_header['first_entry_pointer'] != -1:
                temp_binary.write_integer(entry_header['first_entry_pointer'] + entry_offset_diff, 4)
            else:
                temp_binary.write_integer(-1, 4)
            
            # Update last entry pointer
            if entry_header['last_entry_pointer'] != -1:
                temp_binary.write_integer(entry_header['last_entry_pointer'] + entry_offset_diff, 4)
            else:
                temp_binary.write_integer(-1, 4)
            
            # Update reserved pointer
            if entry_header['reserved_pointer'] != -1:
                temp_binary.write_integer(entry_header['reserved_pointer'] + entry_offset_diff, 4)
            else:
                temp_binary.write_integer(-1, 4)
            
            # 5. Copy and update entries
            current_entry_pos = entry_header['first_entry_pointer']
            
            while current_entry_pos != -1:
                binary_file.goto(current_entry_pos)
                new_entry_pos = current_entry_pos + entry_offset_diff
                temp_binary.goto(new_entry_pos)
                
                # Copy entry ID
                entry_id = binary_file.read_integer(4)
                temp_binary.write_integer(entry_id, 4)
                
                # Copy and update field values
                for field_name, field_type in header['signature']:
                    if field_type == FieldType.INTEGER:
                        # Copy integer field as is
                        value = binary_file.read_integer(4)
                        temp_binary.write_integer(value, 4)
                    elif field_type == FieldType.STRING:
                        # Update string pointer
                        old_string_pos = binary_file.read_integer(4)
                        if old_string_pos in string_position_map:
                            new_string_pos = string_position_map[old_string_pos]
                            temp_binary.write_integer(new_string_pos, 4)
                        else:
                            # If string pointer is invalid, keep it as is
                            temp_binary.write_integer(old_string_pos, 4)
                
                # Update previous entry pointer
                prev_entry_pos = binary_file.read_integer(4)
                if prev_entry_pos != -1:
                    temp_binary.write_integer(prev_entry_pos + entry_offset_diff, 4)
                else:
                    temp_binary.write_integer(-1, 4)
                
                # Update next entry pointer and move to next entry
                next_entry_pos = binary_file.read_integer(4)
                if next_entry_pos != -1:
                    temp_binary.write_integer(next_entry_pos + entry_offset_diff, 4)
                    current_entry_pos = next_entry_pos
                else:
                    temp_binary.write_integer(-1, 4)
                    current_entry_pos = -1  # End of entries
            
            # 6. Update header offsets in the temp file
            temp_binary.goto(header['string_buffer_offset'] - 8)  # Position of string buffer offset in header
            temp_binary.write_integer(new_string_buffer_offset, 4)  # Update string buffer offset
            temp_binary.write_integer(new_first_available_position, 4)  # Update first available position
            temp_binary.write_integer(new_entry_buffer_offset, 4)  # Update entry buffer offset
        
        # 7. Replace original file with temp file
        binary_file.file.close()
        import os
        import shutil
        os.remove(f"{self.name}/{table_name}.table")
        shutil.move(temp_file_path, f"{self.name}/{table_name}.table")
        
        # 8. Reopen the file and return updated header
        with open(f"{self.name}/{table_name}.table", "rb+") as f:
            binary_file.__init__(f)
            updated_header = self._parse_header(binary_file)
            
            # Rebuild string lookup with new positions
            self.string_lookup = {}
            self._build_string_lookup(binary_file, updated_header)
            
            return updated_header

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
                    
            # Write header and get offsets
            string_buffer_offset, entry_buffer_offset = self._write_header(binary_file, field_list)
            print("create_table: String buffer offset:", string_buffer_offset)
            print("create_table: Entry buffer offset:", entry_buffer_offset)
            # Initialize string buffer (16 bytes of zeros)
            self._initialize_string_buffer(binary_file, string_buffer_offset)
            
            # Initialize entry buffer
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
            
            # calculate entry size
            # ID (4 bytes) + field values (4 bytes each) + prev/next pointers (8 bytes)
            entry_size = 4 + len(signature) * 4 + 8
            
            # new entry position
            # add at the end for now
            # TODO: reuse of deleted entries
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
            
            # write next pointer
            binary_file.write_integer(-1, 4)
            
            # if not empty update the previous last entry's next pointer
            if entry_header['nentries'] > 0:
                binary_file.goto(entry_header['last_entry_pointer'] + entry_size - 4)  # pos of next pointer in previous last entry
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
                # skip first entry pointer (keep it as is)
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
    Test data
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

    if db.indexes_built:
        print("Indexes built:", db.indexes)
    if db.string_lookup_built:
        print("String lookup built:", db.string_lookup)

    Clean up
    db.delete_table('cours')
    print("\nCleaned up:", db.list_tables())  # should show []