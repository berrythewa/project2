Here’s a clean, professional, and ready-to-use `README.md` file that you can directly copy/paste into your GitHub repository. It is structured based on the PDF content you provided:

---

# ULDB - Unique Layout for a DataBase

[![Python Version](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

## Table of Contents
1. [Introduction](#introduction)
2. [Project Overview](#project-overview)
3. [Features](#features)
4. [Installation](#installation)
5. [Usage](#usage)
6. [File Structure](#file-structure)
7. [Contributing](#contributing)
8. [License](#license)

---

## Introduction

This project implements a simplified database management system called **ULDB (Unique Layout for a DataBase)** as part of the **INFO-F-106 Projet d’Informatique** course at the Université Libre de Bruxelles (ULB). The goal is to create a binary file-based database system that supports basic operations such as creating tables, inserting entries, querying data, updating entries, and deleting entries.

The project also includes a Command Line Interface (CLI) interpreter for interacting with the database using a custom query language.

---

## Project Overview

The ULDB system is designed to store data in binary files, with each table represented as a separate file. The database supports two types of fields:
- **Integers**: Encoded in little-endian format using two's complement.
- **Strings**: Encoded with a 2-byte length prefix followed by UTF-8 encoded bytes.

The project is divided into five main phases:
1. **Binary File Management**: Reading and writing integers and strings to binary files.
2. **Basic Table Management**: Creating and managing tables with fixed schemas.
3. **Entry Operations**: Inserting, retrieving, and querying entries in tables.
4. **Modification and Deletion**: Updating and deleting entries while optimizing space usage.
5. **CLI Interpreter**: A custom query language for interacting with the database.

A bonus phase involves implementing table joins to handle relationships between tables (e.g., many-to-one, one-to-many).

---

## Features

- **Binary File Handling**: Efficiently read and write integers and strings in binary format.
- **Table Management**: Create, delete, and manage tables with custom schemas.
- **CRUD Operations**: Insert, retrieve, update, and delete entries in tables.
- **Space Optimization**: Reuse deleted entry slots to minimize file size growth.
- **Custom Query Language**: A CLI interpreter for executing database operations using a simple syntax.
- **UTF-8 Support**: Handle non-ASCII characters in strings seamlessly.

---

## Installation

### Prerequisites
- Python 3.8 or higher
- Required libraries: `pytest` (for testing)

### Steps
1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/uldb.git
   cd uldb
   ```

2. Install dependencies:
   ```bash
   pip install pytest
   ```

3. Run tests to ensure everything works:
   ```bash
   pytest test.py
   ```

---

## Usage

### Running the CLI Interpreter
You can interact with the database using the CLI interpreter. Run the following command:
```bash
python uldb.py
```

#### Example Commands
```plaintext
uldb:: open(programme)
uldb:: create_table(cours,MNEM=INTEGER,NOM=STRING,COORD=STRING,CRED=INTEGER)
uldb:: insert_to(cours,MNEM=101,NOM="Progra",CRED=10,COORD="T. Massart")
uldb:: from_if_get(cours,CRED=10,MNEM)
101
uldb:: quit
```

### Using the Database Programmatically
You can also use the `Database` class programmatically in your Python scripts:
```python
from database import Database

db = Database("programme")
db.create_table("cours", ("MNEM", FieldType.INTEGER), ("NOM", FieldType.STRING))
db.add_entry("cours", {"MNEM": 101, "NOM": "Progra"})
entries = db.get_complete_table("cours")
print(entries)
```

---

## File Structure

The project is organized into the following files:

- **`binary.py`**: Handles low-level binary file operations (reading/writing integers and strings).
- **`database.py`**: Implements the core database functionality (table creation, entry management, etc.).
- **`uldb.py`**: Provides the CLI interpreter for interacting with the database.
- **`database_bonus.py`** *(optional)*: Extends the database functionality for the bonus phase (table joins).
- **`test.py`**: Contains unit tests for validating the implementation.

---

## Contributing

Contributions are welcome! If you'd like to contribute, please follow these steps:
1. Fork the repository.
2. Create a new branch for your feature or bug fix:
   ```bash
   git checkout -b feature-name
   ```
3. Commit your changes:
   ```bash
   git commit -m "Add feature or fix"
   ```
4. Push your branch:
   ```bash
   git push origin feature-name
   ```
5. Open a pull request.

---

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Special thanks to the **INFO-F-106 teaching team** at ULB for providing the project guidelines.
- Inspired by real-world database systems and binary file handling techniques.

---