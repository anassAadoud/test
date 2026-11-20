# Partie 07 — T8 : onglet fichier et `/assist` sur un CSV (F3)

**Responsable (commit + push)** : Gouraguine Zakaria (`Zikogouravitch`) · **Semaine** : 3 · **Dépend de** : Partie 06 (T6)
**Ce dossier est le projet complet** : Partie 06 + mises à jour de T8.

## Critère de fin de T8 : atteint ✔, sur la validation

> Pipeline : « Le dépôt de `jeu_independant.csv` affiche 126 lignes triées, cas critiques en tête. »

⚠️ Le jeu indépendant est réservé à la mesure finale (T12) et ne se lit qu'une fois. Le passer dans l'application, ce serait le lire. Le critère est donc vérifié sur **`jeu_validation.csv`**. **À noter dans la fiche de la semaine 3 comme changement.**

Vrai modèle, `POST /assist/csv` :

```
jeu_validation.csv : 120 lignes classées et triées en 1,1 s
critiques en tête : oui · critiques attendus trouvés : 30 / 30 · alertes en plus : 2
```

Les 2 alertes en plus partent chez un technicien plus tôt que nécessaire, sans danger pour l'employé :
- « Nobody can hear me because the microphone… » : le mot « nobody » fait croire que beaucoup de monde est touché ;
- « I lost access to my email after changing my phone number for MFA » : classé en sécurité.

Avec l'extrait Tobi-Bueck (100 tickets longs) : 2,5 s, tri correct.

## Ce qu'on a fait

**1. `support_agent/assistant_fichier.py`** : le traitement d'un fichier.

| Étape | Détail |
| --- | --- |
| Lecture | Détecte le séparateur (`,` `;` tabulation) et l'encodage (UTF-8, UTF-8 BOM d'Excel, Latin-1) |
| Colonne de texte | `text`, `message`, `description`, `body`… ; `subject` est ajouté devant s'il existe |
| Garde-fous | Les lignes vides sont ignorées, les numéros de ligne d'origine gardés ; 2 Mo et 2 000 lignes au plus ; messages d'erreur clairs |
| Par ligne | Catégorie, priorité, critique, **groupe**, **délai**, article, « technicien requis » (règles R1, R2 et R5 de T6) |
| Tri | Critiques d'abord, puis priorité high → medium → low, hors sujet à la fin ; à égalité, l'ordre du fichier est gardé |
| Sorties | Résumé (critiques, technicien requis, indéterminés, hors sujet, par catégorie, par priorité) et CSV trié téléchargeable (s'ouvre bien dans Excel) |

**2. Prédiction par lot** (`ModeleSupport.predire_lot`) : MiniLM encode tout le fichier en une fois. On obtient environ 10 ms par ligne, et les résultats sont identiques à `predire` (testé).

**3. API**

| Route | Rôle |
| --- | --- |
| `POST /assist` | Version JSON : `{"textes": [...]}` |
| `POST /assist/csv` | Version fichier : le CSV envoyé tel quel |

Le CSV est envoyé tel quel, sans formulaire : aucune nouvelle dépendance n'est nécessaire.

**4. Interface** : un 3e onglet, **A file of tickets** (`support_agent/ui/fichier.py`, le nom prévu dans la fiche).
- Dépôt du CSV.
- 4 compteurs : tickets, critiques, technicien requis, hors sujet.
- Alerte rouge s'il y a des cas critiques.
- Tableau trié et bouton de téléchargement.

**5. Correctif de sécurité dans la correction orthographique** (bug introduit en Partie 05, trouvé ici)

En regardant le tri, « We are still waiting for the refund you **promised** » apparaissait en sécurité critique. La correction avait changé **promised → compromised**. Sur la validation, elle modifiait aussi :
- **ransom → random** et **stole → solve** : des cas critiques risquaient d'être cachés ;
- tone → one, renewing → reviewing, choppy → copy.

| Avant | Après |
| --- | --- |
| Tout mot inconnu de l'entraînement pouvait être « corrigé » | Un mot du **dictionnaire** (~21 700 mots entiers du tokenizer MiniLM) n'est jamais touché ; si sa forme de base existe (`renewing` → `renew`), la correction doit commencer par cette base |

- Les vraies fautes restent corrigées (`printr brokn` → `printer broken`, `stoped` → `stopped`).
- Un test vérifie que promised, ransom, stole, renewing et choppy ne bougent plus.
- Le correctif est appliqué aux **Parties 05, 06 et 07**.
- Les 7 phrases « faute de frappe » du jeu indépendant ont été **remplacées une 2e fois** : leurs mots avaient servi à un contrôle de dictionnaire. Le jeu reste à 126 lignes et 32 critiques.

**Mesure de départ recalculée** (validation, modèle réentraîné) :

| Mesure | Avant le correctif | Après |
| --- | --- | --- |
| F1 macro | 0,917 | 0,917 |
| Top-1 | 0,838 | **0,848** |
| Top-3 | 0,962 | 0,962 |
| Critiques manqués | 0/30 | 0/30 |
| Hors sujet refusés | 13/15 | 12/15 |
| Bilan des tickets | 10/10 | 10/10 |

Le refus en moins était obtenu en partie par hasard : « leaking » devenait « leading ». Les JSON de `models/` sont mis à jour dans les Parties 06 et 07.

### Fichiers nouveaux ou modifiés par rapport à la Partie 06

- **Nouveaux** :
  - `support_agent/assistant_fichier.py`, `support_agent/ui/fichier.py`
  - `tests/test_assist.py`
- **Modifiés** :
  - `support_agent/modele.py` : `predire_lot`, correction sûre, `formes_de_base`
  - `support_agent/encodeur.py` : dictionnaire `mots()`
  - `support_agent/api/` : routes `/assist`
  - `support_agent/ui/` : 3e onglet, `assist_csv`
  - `data/eval/jeu_independant.csv` : 7 phrases remplacées
  - `models/*.json`, `docs/modele.md`, `README.md`
  - les tests (conftest, test_saisies, test_modele)

## Qualité du code (Python 3.11, environnement installé depuis le lock)

```
pytest   → 189 passed (couverture 99 %)
ruff     → All checks passed!
mypy     → Success: no issues found in 44 source files
```

## Pour intégrer (Zakaria)

1. Copier tout le contenu de ce dossier à la racine du dépôt, **sauf ce fichier `RESULTATS_…md`**, en gardant `.git`.
2. Vérifier :
   ```powershell
   pip install -r requirements-dev.lock
   pip install -e . --no-deps
   pytest
   ```
3. Essai réel : lancer l'API et l'interface, puis déposer `data/eval/jeu_validation.csv` dans l'onglet **A file of tickets**.
4. Faire le commit, par exemple `T8 : /assist et onglet fichier (CSV trié, critiques en tête) + correctif correction orthographique`, puis push.

## À valider

- [ ] Le critère de T8 vérifié sur la validation au lieu du jeu indépendant (à noter dans la fiche de la semaine 3) ?
- [ ] Le correctif de la correction orthographique (et le 2e remplacement des 7 phrases) ?
