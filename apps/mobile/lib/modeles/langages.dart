// FICHIER GÉNÉRÉ depuis `app/languages.json` — ne pas éditer à la main.
//
// La liste des langages appartient au serveur : `app/languages.py` la lit pour la
// détection, le gabarit Jinja pour son menu déroulant, et le visualiseur pour le mode de
// coloration. Une quatrième copie saisie à la main dériverait, et l'écart serait muet —
// un langage choisi ici et inconnu là-bas donnerait simplement un paste sans coloration.
//
// `test/langages_test.dart` relit le JSON du serveur et échoue si cette liste s'en écarte.
// Régénérer avec `outils/engendrer_langages.py`.

/// Les slugs de langage que l'instance connaît, dans l'ordre du serveur.
const langagesConnus = <String>[
  'bash',
  'c',
  'cpp',
  'csharp',
  'css',
  'diff',
  'dockerfile',
  'go',
  'html',
  'java',
  'javascript',
  'json',
  'kotlin',
  'lua',
  'makefile',
  'markdown',
  'php',
  'python',
  'ruby',
  'rust',
  'sql',
  'swift',
  'toml',
  'typescript',
  'xml',
  'yaml',
];

/// L'extension de fichier principale de chaque langage, pour nommer un partage.
const extensionsParLangage = <String, String>{
  'bash': '.sh',
  'c': '.c',
  'cpp': '.cpp',
  'csharp': '.cs',
  'css': '.css',
  'diff': '.diff',
  'dockerfile': '.dockerfile',
  'go': '.go',
  'html': '.html',
  'java': '.java',
  'javascript': '.js',
  'json': '.json',
  'kotlin': '.kt',
  'lua': '.lua',
  'makefile': '',
  'markdown': '.md',
  'php': '.php',
  'python': '.py',
  'ruby': '.rb',
  'rust': '.rs',
  'sql': '.sql',
  'swift': '.swift',
  'toml': '.toml',
  'typescript': '.ts',
  'xml': '.xml',
  'yaml': '.yaml',
};
