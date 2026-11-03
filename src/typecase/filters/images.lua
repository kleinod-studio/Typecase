-- Alignment of images in exports. An image with the class left, center or right lies in an element
-- that says so: for HTML and PDF the class image-<side> (see BASE_CSS, templates can restyle it);
-- for Word paragraph styles that export.py completes afterwards, since Pandoc only names them.

local docx = FORMAT == "docx"
local sides = {left = true, center = true, right = true}

local function side_of(image)
  for _, class in ipairs(image.classes) do
    if sides[class] then
      return class
    end
  end
end

local function single_image(inlines)
  if #inlines == 1 and inlines[1].t == "Image" then
    return inlines[1]
  end
end

function Figure(figure)
  local first = figure.content[1]
  local image = first and first.content and single_image(first.content)
  local side = image and side_of(image)
  if not side then
    return nil
  end
  if not docx then
    figure.classes:insert("image-" .. side)
    return figure
  end
  -- Word: the image and its caption as two paragraphs with their own styles.
  local blocks = pandoc.List({
    pandoc.Div({pandoc.Para({image})}, {["custom-style"] = "Typecase Image " .. side}),
  })
  local caption = pandoc.utils.blocks_to_inlines(figure.caption.long)
  if #caption > 0 then
    blocks:insert(pandoc.Div({pandoc.Para(caption)}, {["custom-style"] = "Typecase Caption " .. side}))
  end
  return blocks
end

function Para(para)
  local image = single_image(para.content)
  local side = image and side_of(image)
  if not side then
    return nil
  end
  if docx then
    return pandoc.Div({para}, {["custom-style"] = "Typecase Image " .. side})
  end
  return pandoc.Div({para}, {class = "image-" .. side})
end
