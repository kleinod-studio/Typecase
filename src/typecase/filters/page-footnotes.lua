-- For PDF export: keep every footnote where it is called, as <span class="footnote">, so the
-- PDF renderer can float it to the bottom of its page (CSS "float: footnote").
-- Pandoc would otherwise collect all notes at the end of the document.
function Note(note)
  return pandoc.Span(pandoc.utils.blocks_to_inlines(note.content), {class = "footnote"})
end
