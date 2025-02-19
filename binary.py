import io 

class BinaryFile:
    def __init__(self, file: BinaryIO):
        """
            Initializes the BinaryFile class with a binary file opened in read/write mode.
            :param file: binary file object in read/write mode
            :raises TypeError: if file not valid binary file object
            :raises ValueError: if file is not opened with mode supporting read and write
        """
        if not isinstance(file, io.BinaryIO):
            raise TypeError("File must be a valid binary file object (BinaryIO).")
        
        mode = getattr(file, 'mode', '')
        if 'b' not in mode:
            raise ValueError("File must be opened in binary mode ('b').")
        if '+' not in mode and not ('r' in mode and 'w' in mode):
            raise ValueError("Opening mode should support both write and read (e.g., 'rb+', 'wb+').")

        self.file = file

    def get_size(self) -> int:
        """
        Gets the size of the file in bytes.
        :return: Size (integer) of file in bytes.

        """
        #save position
        curr_pos = self.file.tell()
        
        #move to end of file
        self.file.seek(0,2)

        # get file size
        size = self.file.tell()
        
        # restore original positon
        self.file.seek(curr_pos)
        return size

    def goto(self, pos: int) -> None:
        """
        Moves file cursor to specified postion
        :param pos: Position (in bytes)
                    if pos < 0 start from end of file
                    if pos > 0 start from beginning of file
        :raises ValueError: if pos out of bounds
        """
        size = self.get_size()
        # TODO: maybe test bounds here one time ? 
        if not isinstance(pos, int):
            raise TypeError("Pos must be integer")
        if pos <= 0:
            # move from the start of the file
            if pos > size:
                raise ValueError(f"Position {pos} exceeds file size: {size}.")
            self.file.seek(pos, 0)
        else:
            # move from the start of the file
            if abs(pos) > size:
                raise ValueError(f"Positon {-pos} before start of file is invalid.")
            self.file.seek(pos, 2)

    def write_integer(self, n: int, size: int) -> int:
        """
        Writes integer to current position in file using size bytes

        :param n: interger to write
        :param size: number of bytes to use for encoding n
        :return: number of bytes written
        :raises ValueError: if size not valid
        :raises ValueError: if integer cannot be represented in size bytes
        :raises IOError: written bytes different from given size 
        """

        # check size 
        if size not in (1,2,4):
            raise ValueError("Size must be 1,2 or 4 bytes")
        
        # validate the range of the integer
        min_value = -(2**(8*size-1)) #minimum value for two's complement
        max_value = 2 ** (8*size-1) - 1 #maximum value for two's complement
        if not (min_value<=n<=max_value):
            raise ValueError(f"Integer {n} cannot be represented in {size} bytes.")
        
        # convert integer to bytes in little-endian format
        encoded_bytes = n.to_bytes(size, byteorder='little', signed=True)
        
        # write the bytes to the file
        bytes_written = self.file.write(encoded_bytes)
        if size != bytes_written:
            raise IOError(f"Wrong number of bytes {bytes_written} written whilst size is {size}.")
        
        return bytes_written

    def write_integer_to(self, n: int, size: int, pos: int) -> int:
        """
        Writes integer at given position in file
        :param n: integer to write
        :param size: number of bytes used to encode
        :param pos: position at which to write the integer
        :raises ValueError: if size not valid
                            or n cannot be repr in size bytes
        :raises IOError: If writing fails.
        :return: number of bytes successfully written
        """
        if size not in (1,2,4):
            raise ValueError("Size must be 1,2 or 4 bytes")
        
        # save current positon
        curr_pos = self.file.tell()
        
        # goto pos then write and finally restore position
        try:
            self.goto(pos)
            bytes_written = self.write_integer(n, size)
        except Exception as e:
            print(f"Error: {e}")
            bytes_written = 0
        finally:
            try:
                self.goto(curr_pos)
            except Exception as e:
                print(f"Error restoring positon: {e}")

        return bytes_written

    def read_integer(self, size: int) -> int
        """
        Reads integer of size bytes at current position in file
        :param size: number of bytes to supposedly representing the integer
        :return: decoded integer  
        :raises ValueError: if size not valid
        :raises EOFError: if not enough bytes left to read
        """
        # check size 
        if size not in (1,2,4):
            raise ValueError("Size must be 1,2 or 4 bytes")
        
        # check if there enough bytes to read size bytes
        curr_pos = self.file.tell()
        file_size = self.get_size()
        if curr_pos+size > file_size:
            raise ValueError(f"Could not read {size} bytes, out of bounds.")

        # read bytes and convert
        read_bytes = self.file.read(size)
        # extra cautiousness check for out of bounds error
        if len(read_bytes) != size:
            raise EOFError(f"Unexpected end of file while reading {size} bytes at pos {curr_pos}.")

        return int.from_bytes(read_bytes, byteorder='little', signed=True)

    def read_integer_from(self, size: int, pos: int) -> int:
        """
        Reads an integer of size bytes from a specific position in the file
        :param size: number of bytes of the integer
        :param pos: position in the file from which to read the integer.
        :return: decoded integer.
        :raises ValueError: if size is not 1, 2, or 4.
        :raises EOFError: if there are not enough bytes to read.
        :raises IOError: if seeking to pos fails.
        """

        # save current position
        curr_pos = self.file.tell()
        
        try:
            self.goto(pos)
            read_integer = self.read_integer(size)
        except Exception as e:
            print(f"Error: {e}")
            read_integer = None
        finally:
            try:
                self.goto(curr_pos)
            except Exception as e:
                print(f"Error restoring positon: {e}")
        
        return read_integer


    def write_string(self, s: str) -> int:
        """
        Writes UTF-8 encoded string to current file position
        :param s: string to write
        :return: total number of written bytes (length prefix+ string bytes)
        :raises ValueError: if the encoded string exceeds 32,767 bytes
        """
        # constants
        prefix_size = 2
        ULDB_max_str_len = 32767

        # convert str into utf-8
        utf8_s = s.encode("utf-8")
        
        # check if newly encoded string respects ULDB norm fixed size
        utf8_s_size = len(utf8_s)
        if utf8_s_size > ULDB_max_str_len:
            raise ValueError(f"UTF-8 encoded string size {utf8_s_bytes} exceeds {ULDB_max_str_len}.") 
        
        # convert utf8 string size into little-endian bytes
        utf8_s_bytes = utf8_s_size.to_bytes(2, "little", signed=True)

        # bytes to be written
        final_string =  utf8_s_bytes + utf8_s

        self.file.write(final_string)
        return utf8_s_size + prefix_size

    def write_string_to(self, s: str, pos: int) -> int:
        """
        Writes string s in file at pos specified postion
        :param s: string to be written
        :param pos: position in file at which to write
        """
        curr_pos = self.file.tell()
        # goto pos
        self.goto(pos)
        
        # write and retrieve number of bytes written
        bytes_written = self.write_string(s)
        
        # restore pos
        self.goto(curr_pos)

        return bytes_written

    # read_string(self) -> str
    # read_string_from(self, pos: int) -> str
