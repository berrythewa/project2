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
   

    def list_tables(self) -> list[str]:
        """
            Lists all tables in the database.
            :return: list of table names
        """
        return list(self.tables.keys())

    # TABLE INITIALIZATION HELPER FUNCTIONS
    def _initialize_string_buffer(self, binary_file: BinaryFile, offset: int) -> None:
        """
            Initializes the string buffer:
            - Writes a null terminator (0x00) at the given offset
        """
        binary_file.goto(offset)
        for _ in range(16):  # 16 bytes initial size
            binary_file.write_integer(0, 1)

    def _initialize_entry_buffer(self, binary_file: BinaryFile, offset: int) -> None:
        """
            Initializes the entry buffer with 20-byte mini-header:
            - Last used ID (4 bytes): 0
            - Number of entries (4 bytes): 0
            - First entry pointer (4 bytes): -1
            - Last entry pointer (4 bytes): -1
            - Reserved pointer (4 bytes): -1
        """
        binary_file.goto(offset)
        # last used ID
        binary_file.write_integer(0, 4)  
        # number of entries
        binary_file.write_integer(0, 4)  
        # three -1 pointers
        for _ in range(3):  
            binary_file.write_integer(-1, 4)
    
    def _write_header_first_section(self, binary_file: BinaryFile, fields: list[tuple[str, FieldType]]) -> None:
        """
            Writes the first section of the header:
            - Magic constant "ULDB" (4 bytes)
            - Number of fields (4 bytes)
            - Table signature (variable size)
        """
        # write magic constant
        for b in "ULDB".encode('ascii'):
            binary_file.write_integer(b, 1)
        # write number of fields
        binary_file.write_integer(len(fields), 4)
        
        # write signature for each field
        for field_name, field_type in fields:
            # write field type (1 byte)
            binary_file.write_integer(field_type.value, 1)
            # write field name (ULDB format)
            binary_file.write_string(field_name)        

    def _write_offsets(self, binary_file: BinaryFile, string_buffer_offset: int, entry_buffer_offset: int) -> None:
        """
            Writes the offset section:
            - String buffer offset (4 bytes)
            - First available string buffer position (4 bytes)
            - First entry offset (4 bytes)
        """
        # string buffer offset
        binary_file.write_integer(string_buffer_offset, 4)
        # first available position same as start
        binary_file.write_integer(string_buffer_offset, 4)
        # first entry offset
        binary_file.write_integer(entry_buffer_offset, 4)

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
        self.tables[table_name] = [field for field in fields]
        
        table_path = f"{self.name}/{table_name}.table"
        # Ensure database directory exists
        if not os.path.exists(self.name):
            os.makedirs(self.name)
        # write table
        with open(table_path, "wb+") as f:
            binary_file = BinaryFile(f)
            
            # Write header
            self._write_header_first_section(binary_file, [field for field in fields])
            
            # Calculate offsets
            current_pos = binary_file._get_current_pos()
            string_buffer_offset = current_pos
            
            # 16 bytes for string buffer
            entry_buffer_offset = string_buffer_offset + 16  
            
            # Write offsets
            self._write_offsets(binary_file, string_buffer_offset, entry_buffer_offset)
            
            # Initialize buffers
            self._initialize_string_buffer(binary_file, string_buffer_offset)
            self._initialize_entry_buffer(binary_file, entry_buffer_offset)
            self._build_table_index(binary_file, table_name)

    def delete_table(self, table_name: str) -> None:
        """
            Deletes the table of the given name.
            :param table_name: name of the table
            :raises ValueError: if table name does not exist
        """
        table_path = f"{self.name}/{table_name}.table"
        if not os.path.exists(table_path):
            raise ValueError(f"Table {table_name} does not exist")
        os.remove(table_path)
        self.tables.pop(table_name)

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

    # TABLE OPERATIONS HELPER FUNCTIONS
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
        magic_c = magic_c.decode()
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

    def _parse_mini_header(self, binary_file: BinaryFile, header: dict) -> dict:
        """
            Parses the mini header of the table.
            :param binary_file: binary file
            :param header: header of the table
            :return: dict of mini header
        """
        # go to entry buffer  
        binary_file.goto(header['entry_buffer_offset'])
        mini_header = {}
        # read last used ID
        mini_header['last_used_id'] = binary_file.read_integer(4)
        # read number of entries
        mini_header['nentries'] = binary_file.read_integer(4)
        # read first entry pointer
        mini_header['first_entry_pointer'] = binary_file.read_integer(4)
        # read last entry pointer
        mini_header['last_entry_pointer'] = binary_file.read_integer(4)
        # read reserved pointer
        mini_header['reserved_pointer'] = binary_file.read_integer(4)

        # go to start of file
        binary_file.goto(0)
        return mini_header

    def _validate_add_entry_args(self, table_name: str, entry: Entry) -> None:
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
    
    # DB OPERATIONS

    def _build_table_index(self, binary_file: BinaryFile, table_name: str):
        """
            Builds an index for the table of the given name.
            :param table_name: name of the table
        """
        # initialize indexes
        self.indexes[table_name] = {}
        # Initialize indexes for each field
        for field_name, field_type in self.tables[table_name]:
            self.indexes[table_name][field_name] = {}
        
        # headers
        header = self._parse_header(binary_file)
        mini_header = self._parse_mini_header(binary_file, header)

        # If no entries, we're done
        if mini_header['nentries'] == 0:
            return
        # start at first entry
        current_pos = mini_header['first_entry_pointer']
        # read entries
        for _ in range(mini_header['nentries']):
            if current_pos == -1:
                break
            # go to entry
            binary_file.goto(current_pos)
            # Entry Size = 4 (ID) + (n × 4) (fields) + 4 (prev pointer) + 4 (next pointer)
            # read id
            entry_id = binary_file.read_integer(4)
            # read fields
            for field_name, field_type in header['signature']:
                if field_type == FieldType.INTEGER:
                    value = binary_file.read_integer(4)
                else:
                    pointer = binary_file.read_integer(4)
                    value = binary_file.read_string_from(pointer)
                
                # if value is in index, initialize list
                if value not in self.indexes[table_name][field_name]:
                    self.indexes[table_name][field_name][value] = []
                # add to index
                self.indexes[table_name][field_name][value].append(entry_id)
                
            # skip prev pointer
            binary_file.read_integer(4)
            # read next entry pointer
            current_pos = binary_file.read_integer(4)
        
        # update index flag and table list
        self.indexes_built = True
        self.indexes_built_tables.append(table_name) #TODO; getter necessary ?
        # self.open_files[table_name] = binary_file 
        # TODO: keep some tables open ? research, cold vs hot db


    def add_entry(self, table_name: str, entry: Entry) -> None:
        """
            Adds an entry to the table of the given name.
            :param table_name: name of the table
            :param entry: dict[str, Field] to be added to the table
            :raises ValueError: if table name does not exist
            :raises TypeError: if entry is not a dictionary
            :raises ValueError: if entry fields are not compatible with table signature

            Entry size: 16 bytes
            ID: 4 bytes
            Field values: 4 bytes per field
            Pointer to previous entry: 4 bytes
            Pointer to next entry: 4 bytes
        """
        # TODO: if  entry_size is always 16 bytes we can make it a constant
        CST_ENTRY_SIZE = 16
        valid = self._validate_add_entry_args(table_name, entry)
        if not valid:
            raise ValueError("Invalid arguments")
        
        with open(f"{self.name}/{table_name}.table", "r+b") as f:
            binary_file = BinaryFile(f)
            # read offsets
            header = self._parse_header(binary_file)
            # read mini header
            mini_header = self._parse_mini_header(binary_file, header)

            # entry size 
            entry_size = 4  # ID
            entry_size += len(header['signature']) * 4  # 4 bytes/field
            entry_size += 8  # 4 bytes/prev + 4 bytes/next

            # generate unique ID
            new_id = mini_header['last_used_id'] + 1





        
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

    # # Add entries
    # for entry in test_data:
    #     db.add_entry('cours', entry)
    

    if db.indexes_built:
        print(db.indexes)

    # Clean up
    db.delete_table('cours')
    print("\nCleaned up:", db.list_tables())  # should show []