-- Template fields in Word files. A Word file ignores template.html, so the fields a template
-- asks for (a letter's sender, recipient, subject) are put above the text, in the template's
-- order. Each value gets a paragraph style named after the field's key, so a template's
-- reference.docx can style it (or a style of that name is made from Normal).
--   typecase-fields: "sender,recipient,subject"   the keys, set by Typecase

local stringify = pandoc.utils.stringify

local function blocks_of(value)
  local kind = pandoc.utils.type(value)
  if kind == "Inlines" then
    return pandoc.Blocks({pandoc.Para(value)})
  elseif kind == "Blocks" then
    return value
  end
  local text = stringify(value)
  return text ~= "" and pandoc.Blocks({pandoc.Para(pandoc.Inlines(text))}) or pandoc.Blocks({})
end

function Pandoc(doc)
  local keys = doc.meta["typecase-fields"]
  if keys == nil then
    return nil
  end
  local placed = pandoc.List()
  for key in stringify(keys):gmatch("[^,]+") do
    local value = doc.meta[key]
    if value ~= nil then
      local blocks = blocks_of(value)
      if #blocks > 0 then
        placed:insert(pandoc.Div(blocks, pandoc.Attr("", {}, {["custom-style"] = key})))
      end
    end
  end
  if #placed == 0 then
    return nil
  end
  doc.blocks = placed .. doc.blocks
  return doc
end
