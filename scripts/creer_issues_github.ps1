# Crée une issue GitHub par tâche T1..T13 du pipeline (docs/semaine1/4-pipeline.md).
# Prérequis : gh installé et connecté (gh auth login). À lancer UNE fois depuis la racine du dépôt.
$repo = "Zikogouravitch/anass_aadoud-zakaria_gouraguine"
$taches = @(
    @("T1",  "anass0031",      "Dépôt, squelette exécutable, branches et issues"),
    @("T2",  "Zikogouravitch", "Échantillon data/sample et fiche dataset"),
    @("T3",  "anass0031",      "Prototype : incident -> catégorie -> article"),
    @("T4",  "anass0031",      "Schéma Mermaid et captures des 4 écrans"),
    @("T5",  "anass0031",      "Endpoint /chat : conversation, tentatives, question de précision"),
    @("T6",  "Zikogouravitch", "Règles d'escalade et ticket pré-rempli (/tickets)"),
    @("T7",  "Zikogouravitch", "Mesure de départ sur la validation (F1 macro, top-1, top-3)"),
    @("T8",  "Zikogouravitch", "Onglet fichier et /assist sur un CSV"),
    @("T9",  "anass0031",      "Onglet statistiques, /stats et /feedback"),
    @("T10", "anass0031",      "Dockerfile et docker compose (API + interface)"),
    @("T11", "Zikogouravitch", "CI : image Docker et tests, couverture >= 95 %"),
    @("T12", "Zikogouravitch", "Mesure finale sur le jeu indépendant"),
    @("T13", "anass0031",      "Rapport, README final et répétition de la soutenance")
)
foreach ($t in $taches) {
    gh issue create --repo $repo --title "$($t[0]) : $($t[2])" `
        --body "Voir docs/semaine1/4-pipeline.md, ligne $($t[0]) (critère de fin)." `
        --assignee $t[1]
}
