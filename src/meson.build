pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()

install_data(
  [
    'typecase/__init__.py',
    'typecase/__main__.py',
    'typecase/main.py',
    'typecase/config.py',
    'typecase/export.py',
    'typecase/export_dialog.py',
    'typecase/export_templates.py',
    'typecase/fileio.py',
    'typecase/find_bar.py',
    'typecase/formatting.py',
    'typecase/frontmatter.py',
    'typecase/goal.py',
    'typecase/goal_ring.py',
    'typecase/group_view.py',
    'typecase/inspector.py',
    'typecase/keywords.py',
    'typecase/library.py',
    'typecase/markdown_lists.py',
    'typecase/markdown_style.py',
    'typecase/markdown_styler.py',
    'typecase/preferences.py',
    'typecase/search.py',
    'typecase/sheet_editor.py',
    'typecase/textstats.py',
    'typecase/window.py',
  ],
  install_dir: pkgdatadir / 'typecase',
)

# Built-in export templates
install_subdir('typecase/templates', install_dir: pkgdatadir / 'typecase')

launcher = configuration_data()
launcher.set('pkgdatadir', pkgdatadir)
launcher.set('localedir', get_option('prefix') / get_option('localedir'))

configure_file(
  input: 'typecase.in',
  output: 'typecase',
  configuration: launcher,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)
