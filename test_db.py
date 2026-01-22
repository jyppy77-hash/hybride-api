#!/usr/bin/env python3
"""
Test de connexion Cloud SQL pour LotoIA
========================================

Script de validation de la connexion a la base de donnees.
Teste la connexion, compte les tirages, et affiche les infos.

Usage:
    python test_db.py

Exit codes:
    0 = Succes
    1 = Erreur
"""

import sys

def main():
    print()
    print("=" * 55)
    print("  TEST CONNEXION CLOUD SQL - LotoIA")
    print("=" * 55)
    print()

    try:
        # Import du module de connexion
        from db_cloudsql import (
            get_connection,
            get_environment,
            test_connection,
            get_tirages_count,
            get_latest_tirage
        )

        print(f"1. Detection environnement...")
        env = get_environment()
        print(f"   Environnement : {env}")
        print()

        print(f"2. Test de connexion...")
        result = test_connection()

        if result['status'] != 'ok':
            print(f"   ERREUR : {result.get('error', 'Connexion echouee')}")
            print()
            print("=" * 55)
            print("  ECHEC - Verifiez votre configuration")
            print("=" * 55)
            return 1

        print(f"   Connexion reussie a {result['database']}")
        print(f"   Version MySQL : {result['mysql_version']}")
        print()

        print(f"3. Verification des donnees...")
        total = result['total_tirages']
        date_min = result['date_min']
        date_max = result['date_max']

        print(f"   Nombre de tirages : {total}")
        print(f"   Periode : {date_min} -> {date_max}")
        print()

        print(f"4. Test du dernier tirage...")
        latest = get_latest_tirage()
        if latest:
            print(f"   Date : {latest.get('date_de_tirage', 'N/A')}")
            nums = [
                latest.get('boule_1'),
                latest.get('boule_2'),
                latest.get('boule_3'),
                latest.get('boule_4'),
                latest.get('boule_5')
            ]
            chance = latest.get('numero_chance')
            print(f"   Numeros : {nums}")
            print(f"   Chance : {chance}")
        else:
            print("   Aucun tirage trouve")
        print()

        print("=" * 55)
        print(f"  SUCCES - {total} tirages trouves")
        print(f"  Environnement : {env}")
        print("=" * 55)
        print()

        return 0

    except ImportError as e:
        print(f"   ERREUR IMPORT : {e}")
        print()
        print("   Verifiez que db_cloudsql.py existe et que")
        print("   les dependances sont installees :")
        print("   pip install pymysql python-dotenv")
        print()
        print("=" * 55)
        print("  ECHEC - Module non trouve")
        print("=" * 55)
        return 1

    except ValueError as e:
        print(f"   ERREUR CONFIG : {e}")
        print()
        print("   Creez un fichier .env avec :")
        print("   DB_PASSWORD=votre_mot_de_passe")
        print()
        print("=" * 55)
        print("  ECHEC - Configuration manquante")
        print("=" * 55)
        return 1

    except Exception as e:
        print(f"   ERREUR : {e}")
        print()
        print("=" * 55)
        print("  ECHEC - Erreur inattendue")
        print("=" * 55)
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
