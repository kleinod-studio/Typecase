i18n = import('i18n')

# The desktop entry and the metainfo get their translations from po/ at build time.
desktop_file = i18n.merge_file(
  input: 'studio.kleinod.Typecase.desktop.in',
  output: 'studio.kleinod.Typecase.desktop',
  type: 'desktop',
  po_dir: '../po',
  install: true,
  install_dir: get_option('datadir') / 'applications',
)

metainfo_file = i18n.merge_file(
  input: 'studio.kleinod.Typecase.metainfo.xml.in',
  output: 'studio.kleinod.Typecase.metainfo.xml',
  po_dir: '../po',
  install: true,
  install_dir: get_option('datadir') / 'metainfo',
)

desktop_file_validate = find_program('desktop-file-validate', required: false)
if desktop_file_validate.found()
  test('validate-desktop', desktop_file_validate, args: [desktop_file])
endif

appstreamcli = find_program('appstreamcli', required: false)
if appstreamcli.found()
  test('validate-metainfo', appstreamcli, args: ['validate', '--no-net', '--explain', metainfo_file])
endif

install_data(
  'studio.kleinod.Typecase.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/scalable/apps',
)

install_data(
  'studio.kleinod.Typecase-symbolic.svg',
  install_dir: get_option('datadir') / 'icons/hicolor/symbolic/apps',
)
