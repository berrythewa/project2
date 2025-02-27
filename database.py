from enum import IntEnum
from binary import BinaryFile
import os

# field type enum
class FieldType(IntEnum):
    INTEGER = 1
    STRING = 2

# type alias for table signature
TableSignature = list[tuple[str, FieldType]]

# database class
class Database:
    def __init__(self, name: str):
        self.name = name
        self.tables: dict[str, list[tuple[str, FieldType]]] = {}

    def list_tables(self) -> list[str]:
        """
            Lists all tables in the database.
            :return: list of table names
        """
        return list(self.tables.keys())
    
    def _write_header(self, binary_file: BinaryFile, table_name: str, fields: list[tuple[str, FieldType]]) -> None:
        """
            Writes the header section:
            - Magic constant "ULDB" (4 bytes)
            - Number of fields (4 bytes)
            - Table signature (variable size)
        """
        binary_file.write_string("ULDB")
        binary_file.write_integer(len(fields), 4)
        
        # Write signature for each field
        for field_name, field_type in fields:
            # write field type (1 byte)
            binary_file.write_integer(field_type.value, 1)
            # write field name (ULDB format)
            binary_file.write_string(field_name)

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
            self._write_header(binary_file, table_name, [field for field in fields])
            
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

if __name__ == "__main__":
    db = Database('programme')
    db.create_table(
        'cours',
        ('MNEMONIQUE', FieldType.INTEGER),
        ('NOM', FieldType.STRING),
        ('COORDINATEUR', FieldType.STRING),
        ('CREDITS', FieldType.INTEGER)
    )
    print(db.list_tables()) # doit afficher ['cours']
    db.delete_table('cours')
    print(db.list_tables()) # doit afficher []
    db.delete_table('cours') # doit lancer une exception