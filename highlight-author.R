## input expects: 1) name of author; 2) path to qmd file
.input <- commandArgs(trailingOnly = TRUE)
output <- readLines(con = .input[2])
output <- gsub(.input[1], sprintf("**%s**", .input[1]),
               output)
writeLines(output, .input[2])
