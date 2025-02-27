# TODO - Partie 2 : Gestion basique des tables

## Objectif
Implémenter une gestion de base des tables dans une base de données ULDB. Cela inclut la création, la suppression et la récupération des signatures des tables.

---

## Étapes à suivre

### 1. Définir l'énumération `FieldType`
- Créer une énumération entière `FieldType` dans le fichier `database.py`.
- Ajouter deux constantes : `INTEGER` et `STRING`.

#### Code attendu :
```python
from enum import IntEnum

class FieldType(IntEnum):
    INTEGER = 1
    STRING = 2
```

---

### 2. Définir le type alias `TableSignature`
- Utiliser un alias de type pour représenter la signature d'une table.
- La signature est une liste de paires `(nom_du_champ, type_du_champ)`.

#### Code attendu :
```python
TableSignature = list[tuple[str, FieldType]]
```

---

### 3. Implémenter la classe `Database`
Créer une classe `Database` avec les méthodes suivantes :

#### a) Constructeur `__init__`
- Initialiser une base de données avec un nom donné.
- Stocker les tables dans un dictionnaire ou un autre structure appropriée.

#### b) Méthode `list_tables`
- Retourner une liste contenant les noms de toutes les tables existantes dans la base de données.

#### c) Méthode `create_table`
- Créer une nouvelle table avec un nom spécifié et une signature donnée.
- Si la table existe déjà, lever une exception `ValueError`.

#### d) Méthode `delete_table`
- Supprimer la table spécifiée par son nom.
- Si la table n'existe pas, lever une exception `ValueError`.

#### e) Méthode `get_table_signature`
- Récupérer et retourner la signature de la table spécifiée.
- Si la table n'existe pas, lever une exception `ValueError`.

---

### 4. Structure interne des fichiers de table
Chaque table est stockée dans un fichier binaire avec trois sections principales :
1. **Header** : Contient des informations générales sur la table.
2. **String buffer** : Stocke toutes les chaînes de caractères.
3. **Entry buffer** : Contient les données des entrées sous forme de liste chaînée.

#### Détails du formatage :
- Le header doit contenir :
  - Une constante magique `"ULDB"` (4 bytes).
  - Le nombre de champs (4 bytes).
  - La signature de la table (taille variable).
  - L'offset du string buffer (4 bytes).
  - La première place disponible dans le string buffer (4 bytes).
  - L'offset de la première entrée (4 bytes).

- Le string buffer doit avoir une taille qui est une puissance de 2, initialisée à 16 bytes.

- L'entry buffer commence par un mini-header (20 bytes) contenant :
  - Le dernier ID utilisé (4 bytes).
  - Le nombre d'entrées présentes (4 bytes).
  - Un pointeur vers la première entrée (4 bytes).
  - Un pointeur vers la dernière entrée (4 bytes).
  - Un pointeur réservé (4 bytes).

---

### 5. Exemple d'utilisation
Vérifier que les méthodes fonctionnent comme prévu avec cet exemple :

```python
db = Database('programme')
db.create_table(
    'cours',
    ('MNEMONIQUE', FieldType.INTEGER),
    ('NOM', FieldType.STRING),
    ('COORDINATEUR', FieldType.STRING),
    ('CREDITS', FieldType.INTEGER)
)
print(db.list_tables())  # Doit afficher ['cours']
db.delete_table('cours')
print(db.list_tables())  # Doit afficher []
```

---

### 6. Tests automatiques
Écrire des tests pour vérifier le bon fonctionnement des méthodes. Par exemple :
- Vérifier que `create_table` crée une table correctement.
- Vérifier que `delete_table` supprime une table existante.
- Vérifier que `get_table_signature` retourne la bonne signature.

---

### 7. Remarques importantes
- Toutes les exceptions doivent être de type `ValueError` lorsque les opérations ne sont pas possibles.
- Les fichiers binaires doivent respecter strictement le format ULDB décrit dans la documentation.
- Utiliser les fonctions du fichier `binary.py` pour lire et écrire les données dans les fichiers binaires.

---

## Checklist finale
- [ ] Implémenter l'énumération `FieldType`.
- [ ] Définir le type alias `TableSignature`.
- [ ] Implémenter la classe `Database` avec toutes les méthodes requises.
- [ ] Vérifier que les fichiers binaires respectent le format ULDB.
- [ ] Écrire des tests pour valider le bon fonctionnement.
- [ ] Assurer que le code est bien documenté et lisible.

---

Si vous avez besoin d'aide pour une étape spécifique, n'hésitez pas à demander ! 😊