-- Cover page and table of contents for exports, in front of the text.
-- Typecase switches them on with metadata (so any template works, even one that knows nothing
-- about them):
--   typecase-cover: true         title, subtitle, author and date on a page of their own
--   typecase-toc: "2"            a table of contents with that many heading levels
--   typecase-toc-title: "…"      its heading, in the user's language
-- For HTML and PDF they become <div class="cover"> and <div class="toc">; CSS sets the pages.
-- For Word they use the reference document's paragraph styles and a TOC field.

local stringify = pandoc.utils.stringify
local docx = FORMAT == "docx"

local function inlines_of(value)
  if pandoc.utils.type(value) == "Inlines" then
    return value
  end
  return pandoc.Inlines(stringify(value))
end

local function values_of(value)
  if pandoc.utils.type(value) == "List" then
    return value
  end
  return {value}
end

local function xml_escape(text)
  return (text:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;"):gsub('"', "&quot;"))
end

local page_break = pandoc.RawBlock("openxml", '<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

local function cover(meta)
  local blocks = pandoc.List()
  for _, field in ipairs({"title", "subtitle", "author", "date"}) do
    if meta[field] ~= nil then
      for _, value in ipairs(values_of(meta[field])) do
        if docx then
          local style = field:sub(1, 1):upper() .. field:sub(2)
          blocks:insert(pandoc.Div(pandoc.Para(inlines_of(value)), {["custom-style"] = style}))
        else
          blocks:insert(pandoc.Div(pandoc.Plain(inlines_of(value)), {class = field}))
        end
      end
      -- Printed here instead of by the template, so it does not appear twice
      meta[field] = nil
    end
  end
  if docx then
    blocks:insert(page_break)
    return blocks
  end
  return pandoc.List({pandoc.Div(blocks, {class = "cover"})})
end

local function top_level(blocks)
  local top = 6
  for _, block in ipairs(blocks) do
    if block.t == "Header" and block.level < top then
      top = block.level
    end
  end
  return top
end

-- Word's TOC field with its entries already filled in as links, so every program shows them right
-- away. Page numbers need a layout: they appear when the field is updated (Word offers that on
-- opening; w:dirty asks for it). The content control marks it as a table of contents for updating.
local function word_contents(doc, first, last, title)
  local field_start = '<w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>' ..
    string.format('<w:r><w:instrText xml:space="preserve">TOC \\o "%d-%d" \\h \\z \\u</w:instrText></w:r>', first, last) ..
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
  local field_end = '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
  local entries, indents = {}, {}
  for _, block in ipairs(doc.blocks) do
    if block.t == "Header" and block.level >= first and block.level <= last then
      local text = stringify(block.content:walk({Note = function() return {} end}))
      local number = #entries + 1
      -- Our own bookmark, since the names of Pandoc's differ between versions
      block.content:insert(1, pandoc.RawInline("openxml", string.format(
        '<w:bookmarkStart w:id="%d" w:name="typecase_toc_%d"/><w:bookmarkEnd w:id="%d"/>', 900000 + number, number, 900000 + number)))
      entries[number] = string.format(
        '<w:hyperlink w:anchor="typecase_toc_%d" w:history="1"><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:hyperlink>',
        number, xml_escape(text))
      indents[#entries] = (block.level - first) * 280
    end
  end
  local paragraphs = {}
  for index, entry in ipairs(entries) do
    paragraphs[index] = string.format('<w:p><w:pPr><w:ind w:left="%d"/></w:pPr>', indents[index]) ..
      (index == 1 and field_start or "") .. entry .. (index == #entries and field_end or "") .. "</w:p>"
  end
  if #entries == 0 then
    paragraphs[1] = "<w:p>" .. field_start .. field_end .. "</w:p>"
  end
  return '<w:sdt><w:sdtPr><w:docPartObj><w:docPartGallery w:val="Table of Contents"/><w:docPartUnique/></w:docPartObj></w:sdtPr><w:sdtContent>' ..
    string.format('<w:p><w:pPr><w:pStyle w:val="TOCHeading"/></w:pPr><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>', xml_escape(title)) ..
    table.concat(paragraphs) .. "</w:sdtContent></w:sdt>"
end

local function contents(doc, depth, title)
  local first = top_level(doc.blocks)
  local last = math.min(first + depth - 1, 6)
  if docx then
    return pandoc.List({pandoc.RawBlock("openxml", word_contents(doc, first, last, title)), page_break})
  end
  local list = pandoc.structure.table_of_contents(doc.blocks, {toc_depth = last})
  local heading = pandoc.Div(pandoc.Plain(pandoc.Inlines(title)), {class = "toc-title"})
  return pandoc.List({pandoc.Div({heading, list}, {id = "TOC", class = "toc"})})
end

function Pandoc(doc)
  local meta = doc.meta
  local front = pandoc.List()
  if meta["typecase-cover"] then
    if meta.title ~= nil and meta.pagetitle == nil then
      meta.pagetitle = stringify(meta.title)  -- the HTML page still needs a window title
    end
    front:extend(cover(meta))
  end
  if meta["typecase-toc"] then
    local depth = tonumber(stringify(meta["typecase-toc"])) or 2
    local title = meta["typecase-toc-title"] and stringify(meta["typecase-toc-title"]) or "Contents"
    front:extend(contents(doc, depth, title))
  end
  doc.blocks = front .. doc.blocks
  doc.meta = meta
  return doc
end
