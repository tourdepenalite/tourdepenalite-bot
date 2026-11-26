"""Verifie le jeton Instagram et affiche l'ID du compte : python -m tdp.check_instagram"""
from . import config, publish

if __name__ == "__main__":
    accounts = publish.my_instagram_accounts()
    for a in accounts:
        print("Compte Instagram :", a)
    if not accounts:
        print("Aucun compte renvoye : verifier le jeton et l'hote", config.IG_GRAPH_HOST)
    if config.IG_USER_ID:
        print("Quota de publication :", publish.quota())
