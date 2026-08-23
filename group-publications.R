## input expects: 1) bib file; 2) path to qmd file
.input <- commandArgs(trailingOnly = TRUE)

strip_year <- function(year) {
  trimws(gsub("^[{'\"]+|[}'\"]+$", "", year))
}

bib_lines <- readLines(.input[1], warn = FALSE)
entry_starts <- grep("^@\\w+\\s*\\{", bib_lines)
entry_ends <- c(entry_starts[-1] - 1, length(bib_lines))

years <- setNames(character(), character())
for (i in seq_along(entry_starts)) {
  entry <- paste(bib_lines[entry_starts[i]:entry_ends[i]], collapse = "\n")
  key <- sub("^@\\w+\\s*\\{\\s*([^,]+),.*$", "\\1", bib_lines[entry_starts[i]],
             perl = TRUE)
  body <- sub("^[^\n]*\n?", "", entry, perl = TRUE)
  year_match <- regexpr("(?i)\\byear\\s*=\\s*(\\{[^{}]*\\}|\"[^\"]*\"|[^,\n]+)",
                        body, perl = TRUE)
  if (year_match > 0) {
    year_field <- regmatches(body, year_match)
    years[key] <- strip_year(sub("(?i)^\\s*year\\s*=\\s*", "", year_field,
                                 perl = TRUE))
  }
}

lines <- readLines(.input[2], warn = FALSE)
entry_starts <- grep("^::: \\{#ref-[^ ]+ \\.csl-entry\\}$", lines)

get_key <- function(line) {
  sub("^::: \\{#ref-([^ ]+) \\.csl-entry\\}$", "\\1", line)
}

blocks <- vector("list", length(entry_starts))
for (i in seq_along(entry_starts)) {
  start <- entry_starts[i]
  next_entry <- if (i < length(entry_starts)) entry_starts[i + 1] - 1 else length(lines)
  candidates <- which(lines[start:next_entry] == ":::") + start - 1
  end <- candidates[1]
  key <- get_key(lines[start])
  year <- if (key %in% names(years)) years[[key]] else NA_character_
  if (is.na(year) || !nzchar(year)) {
    year <- "n.d."
  }
  block <- lines[start:end]
  if (year != "n.d.") {
    block <- sub("\\(n\\.d\\.\\)", sprintf("(%s)", year), block, perl = TRUE)
  }
  category <- if (grepl("\\+$", year)) "In press" else year
  blocks[[i]] <- list(key = key, year = year, category = category, text = block)
}

category_rank <- function(category) {
  numeric_year <- suppressWarnings(as.integer(sub("^.*?([0-9]{4}).*$", "\\1", category)))
  ifelse(is.na(numeric_year), -Inf, numeric_year)
}

category_labels <- unique(vapply(blocks, `[[`, character(1), "category"))
category_labels <- category_labels[
  order(category_labels == "In press", category_rank(category_labels),
        decreasing = TRUE)
]

anchor <- function(category) {
  paste0("year-", gsub("[^[:alnum:]]+", "-", tolower(category)))
}

nav <- paste(sprintf("[%s](#%s)", category_labels,
                     vapply(category_labels, anchor, character(1))),
             collapse = " · ")

output <- c("# Publications", "", nav, "")
for (category in category_labels) {
  output <- c(output,
              sprintf("## %s {#%s}", category, anchor(category)),
              "",
              "::: {.references .csl-bib-body .hanging-indent entry-spacing=\"1\" line-spacing=\"2\"}")
  category_blocks <- blocks[vapply(blocks, function(block) identical(block$category, category),
                                   logical(1))]
  for (block in category_blocks) {
    output <- c(output, block$text, "")
  }
  output <- c(output, ":::", "")
}

writeLines(output, .input[2])
