function Pandoc (doc)
  local references = pandoc.utils.references(doc)
  doc.blocks = pandoc.Blocks{
    pandoc.Header(1, "Publications"),
    pandoc.Div({}, "list")
  }
  return pandoc.utils.citeproc(doc)
end
