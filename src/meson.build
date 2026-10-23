python = import('python').find_installation('python3')

python.install_sources(
  [
    'typecase/__init__.py',
    'typecase/__main__.py',
    'typecase/main.py',
    'typecase/config.py',
    'typecase/fileio.py',
    'typecase/library.py',
    'typecase/markdown_lists.py',
    'typecase/sheet_editor.py',
    'typecase/window.py',
  ],
  subdir: 'typecase',
)

install_data(
  'typecase.in',
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
  rename: 'typecase',
)
