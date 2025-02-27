import io
from typing import BinaryIO

class BinaryFile:
    def __init__(self, file: BinaryIO):
        """
            Initializes the BinaryFile class with a binary file opened in read/write mode.
            :param file: binary file object in read/write mode
            :raises TypeError: if file not valid binary file object
            :raises ValueError: if file is not opened with mode supporting read and write
        """
        # Check if object has the required binary file methods
        required_methods = ['read', 'write', 'seek', 'tell']
        if not all(hasattr(file, method) for method in required_methods):
            raise TypeError("File must be a binary file object with read/write/seek/tell methods.")
        
        # Check file mode
        mode = getattr(file, 'mode', '')
        if 'b' not in mode:
            raise ValueError("File must be opened in binary mode ('b').")
        if '+' not in mode and not ('r' in mode and 'w' in mode):
            raise ValueError("Opening mode should support both write and read (e.g., 'rb+', 'wb+').")

        self.file = file

    def _get_current_pos(self) -> int:
        """
        Gets the current position in the file.
        :return: Current position in the file.
        """
        return self.file.tell()

    def _get_size(self) -> int:
        """
        Gets the size of the file in bytes.
        :return: Size (integer) of file in bytes.
        :raises IOError: if seeking fails
        """
        # save current position
        curr_pos = self.file.tell()
        size = 0
        
        try:
            # move to end of file
            self.file.seek(0, 2)  # 2 means seek from end
            size = self.file.tell()
        except Exception as e:
            print(f"Error getting file size: {e}")
            raise IOError(f"Failed to get file size: {str(e)}")
        finally:
            try:
                # restore original position
                self.file.seek(curr_pos, 0)  # 0 means seek from start
            except Exception as e:
                print(f"Error restoring position: {e}")
        
        return size

    def goto(self, pos: int) -> None:
        """
        Moves file cursor to specified position
        :param pos: Position (in bytes)
                    if pos < 0 start from end of file
                    if pos > 0 start from beginning of file
        :raises ValueError: if pos out of bounds
        """
        size = self._get_size()
        if not isinstance(pos, int):
            raise TypeError("Pos must be integer")
        
        # for negative positions, convert to offset from end
        if pos < 0:
            pos = size + pos
            
        # check bounds
        if pos > size or pos < 0:
            raise ValueError(f"Position {pos} out of bounds.")
        
        # safely seek to pos
        self.file.seek(pos, 0)

    def write_integer(self, n: int, size: int) -> int:
        """
        Writes integer to current position in file using size bytes

        :param n: integer to write
        :param size: number of bytes to use for encoding n
        :return: number of bytes written
        :raises ValueError: if size not valid
        :raises ValueError: if integer cannot be represented in size bytes
        :raises IOError: if writing fails
        """
        # check size 
        if size not in (1,2,4):
            raise ValueError("Size must be 1,2 or 4 bytes")
        
        # validate the range of the integer
        min_value = -(2**(8*size-1)) #minimum value for two's complement
        max_value = 2 ** (8*size-1) - 1 #maximum value for two's complement
        if not (min_value<=n<=max_value):
            raise ValueError(f"Integer {n} cannot be represented in {size} bytes.")
        
        # Save initial position in case we need to restore on error
        initial_pos = self.file.tell()
        bytes_written = 0
        
        try:
            # convert integer to bytes in little-endian format
            encoded_bytes = n.to_bytes(size, byteorder='little', signed=True)
            
            # write the bytes to the file
            bytes_written = self.file.write(encoded_bytes)
            if bytes_written != size:
                raise IOError(f"Wrong number of bytes {bytes_written} written whilst size is {size}.")
            
        except Exception as e:
            # Restore position on any error
            try:
                self.file.seek(initial_pos)
            except Exception as seek_error:
                print(f"Error restoring position: {seek_error}")
            raise IOError(f"Failed to write integer: {str(e)}")
        
        return bytes_written

    def write_integer_to(self, n: int, size: int, pos: int) -> int:
        """
        Writes integer at given position in file
        :param n: integer to write
        :param size: number of bytes used to encode
        :param pos: position at which to write the integer
        :return: number of bytes written (0 if write fails)
        :raises ValueError: if size not valid, position invalid, or n cannot be represented in size bytes
        """
        # save current position
        curr_pos = self.file.tell()
        bytes_written = 0
        
        try:
            self.goto(pos)  # Let ValueError from invalid position propagate
            bytes_written = self.write_integer(n, size)  # Let ValueError and IOError propagate
        except Exception:
            # Only restore position on error
            try:
                self.goto(curr_pos)
            except Exception as e:
                print(f"Error restoring position: {e}")
            bytes_written = 0  # Nothing was written if any error occurred
            raise  # Re-raise the original error
        
        return bytes_written

    def read_integer(self, size: int) -> int:
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
        file_size = self._get_size()
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
        :return: decoded integer
        :raises ValueError: if size is not 1, 2, or 4
        :raises EOFError: if there are not enough bytes to read
        :raises IOError: if seeking to pos fails
        """
        # save current position
        curr_pos = self.file.tell()
        read_integer = 0
        
        try:
            self.goto(pos)  # Let ValueError from invalid position propagate
            read_integer = self.read_integer(size)  # Let ValueError and EOFError propagate
        except Exception:
            # Only restore position on error
            try:
                self.goto(curr_pos)
            except Exception as e:
                print(f"Error restoring position: {e}")
            raise  # Re-raise the original error
        
        return read_integer

    def write_string(self, s: str) -> int:
        """
        Writes UTF-8 encoded string to current file position.
        String format:
            - 2-byte signed integer prefix (0 to 32767) indicating the number of UTF-8 bytes
            - UTF-8 encoded string of length prefix
        
        :param s: string to write
        :return: total number of written bytes (2-byte length prefix + string bytes)
        :raises ValueError: if the encoded string exceeds 32,767 bytes (ULDB max length)
        :raises TypeError: if s is not a string
        :raises IOError: if writing fails
        """
        if not isinstance(s, str):
            raise TypeError("Input must be a string")

        # Convert string to UTF-8 bytes
        utf8_bytes = s.encode("utf-8")
        utf8_length = len(utf8_bytes)
        
        # Validate ULDB string length constraint (0 to 32767 bytes)
        if utf8_length > 32767:  # 2^15 - 1
            raise ValueError(f"UTF-8 encoded string length ({utf8_length} bytes) exceeds ULDB maximum of 32,767 bytes")
        
        # Write 2-byte length prefix - let its errors propagate
        prefix_bytes_written = self.write_integer(utf8_length, 2)
        
        # Save position after prefix for potential restoration
        after_prefix_pos = self.file.tell()
        bytes_written = prefix_bytes_written
        
        try:
            # Write UTF-8 encoded string
            string_bytes_written = self.file.write(utf8_bytes)
            if string_bytes_written != utf8_length:
                raise IOError(f"Failed to write complete string: wrote {string_bytes_written} of {utf8_length} bytes")
            
            bytes_written += string_bytes_written
            
        except Exception as e:
            # Restore position to after prefix on string content error
            try:
                self.file.seek(after_prefix_pos)
            except Exception as seek_error:
                print(f"Error restoring position: {seek_error}")
            raise IOError(f"Failed to write string content: {str(e)}")
        
        return bytes_written

    def write_string_to(self, s: str, pos: int) -> int:
        """
        Writes string s in file at pos specified position
        :param s: string to be written
        :param pos: position in file at which to write
        :return: number of bytes written (0 if write fails)
        :raises ValueError: if position is invalid
        """
        # save current position
        curr_pos = self.file.tell()
        bytes_written = 0
        
        try:
            # goto pos
            self.goto(pos)
            
            # write and retrieve number of bytes written
            bytes_written = self.write_string(s)
            
        except Exception as e:
            # Only restore position on error
            try:
                self.goto(curr_pos)
            except Exception as e:
                print(f"Error restoring position: {e}")
            # Any error during writing results in 0 bytes written
            bytes_written = 0
            print(f"Error writing string: {e}")
            raise
        
        return bytes_written

    def read_string(self) -> str:
        """
        Reads a string from the current position in the file.
        String format:
            - 2-byte signed integer prefix (0 to 32767) indicating the number of UTF-8 bytes
            - UTF-8 encoded string of length prefix
        
        :return: decoded string
        :raises EOFError: if unable to read the complete string
        :raises ValueError: if string length prefix is invalid (negative or > 32767)
        :raises UnicodeDecodeError: if bytes cannot be decoded as UTF-8
        """
        # read 2 first bytes, length of the string
        try:
            prefix = self.read_integer(2)  # Read 2-byte signed integer
        except EOFError:
            raise EOFError("Unable to read string length prefix")
        
        # According to ULDB format, string length must be between 0 and 32767 (2^15 - 1)
        if prefix < 0 or prefix > 32767:
            raise ValueError(f"Invalid string length prefix: {prefix}. Must be between 0 and 32767.")
        
        # read the string bytes
        try:
            string_bytes = self.file.read(prefix)
            if len(string_bytes) != prefix:
                raise EOFError(f"Expected {prefix} bytes but got {len(string_bytes)} bytes")
            # decode the UTF-8 bytes into a string
            decoded_string = string_bytes.decode('utf-8')
        except UnicodeDecodeError as e:
            decoded_string = '' # check rules if return non or empty string in case of error
            raise UnicodeDecodeError("Unable to decode bytes as UTF-8", e.object, e.start, e.end, e.reason)
        return decoded_string

    def read_string_from(self, pos: int) -> str:
        """
        Reads a string from the specified position in the file.
        :param pos: position in the file from which to read the string
        :return: decoded string
        :raises ValueError: if position is invalid
        :raises EOFError: if unable to read the complete string
        :raises UnicodeDecodeError: if bytes cannot be decoded as UTF-8
        """
        # save current position
        curr_pos = self.file.tell()
        return_string = ''
        
        try:
            self.goto(pos)  # Let ValueError from invalid position propagate
            return_string = self.read_string()  # Let all errors propagate
        except Exception:
            # Only restore position on error
            try:
                self.goto(curr_pos)
            except Exception as e:
                print(f"Error restoring position: {e}")
            raise  # Re-raise the original error
        
        return return_string
