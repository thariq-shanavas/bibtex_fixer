# BibTeX Fixer

A Python tool that automatically fixes and enhances BibTeX entries using the CrossRef API. This tool helps clean up incomplete or malformed bibliography entries by fetching accurate publication information from CrossRef's comprehensive academic database. 

There is no guarantee of reliability, since matching a malformed bibtex entry to a real publication is a fool's errand. Please manually examine the output file after processing.

## Features

- **Parallel Processing**: Uses multithreading for fast processing of large bibliographies
- **CrossRef API Integration**: Fetches accurate publication data from CrossRef
- **Multiple Search Methods**: Searches by DOI, title, or author+title combinations
- **Smart Matching**: Uses fuzzy matching to find the best matches for entries
- **Field Cleaning**: Removes unwanted fields (abstract, keywords) and cleans formatting
- **Customizable Output**: Maintains proper BibTeX formatting with ordered fields

## Installation

### Prerequisites

```bash
pip install requests bibtexparser fuzzywuzzy python-Levenshtein
```

### Dependencies

- `requests` - HTTP library for API calls
- `bibtexparser` - BibTeX file parsing and writing
- `fuzzywuzzy` - Fuzzy string matching
- `python-Levenshtein` - Fast string similarity calculations

## Usage

### Basic Usage

```bash
python bibtex_fixer.py input.bib
```

This will create a fixed version named `input_fixed.bib`.

### Advanced Usage

```bash
# Specify output file
python bibtex_fixer_v4.py input.bib -o output.bib

# Provide email for CrossRef API (recommended for higher rate limits)
python bibtex_fixer_v4.py input.bib -e your.email@example.com

# Use custom number of threads
python bibtex_fixer_v4.py input.bib -t 10

# Combine options
python bibtex_fixer_v4.py input.bib -o clean_bibliography.bib -e your.email@example.com -t 8
```

### Command Line Options

- `input_file`: Path to the input BibTeX file (required)
- `-o, --output`: Output file path (default: `input_file_fixed.bib`)
- `-e, --email`: Email address for CrossRef API identification (recommended)
- `-t, --threads`: Number of threads for parallel processing (default: 6)
- `--max-workers`: Alias for `--threads`

## Examples

### Example 1: Basic Cleanup

**Input BibTeX entry:**
```bibtex
@article{smith2020,
  title={machine learning applications},
  author={Smith, John},
  abstract={This paper discusses various applications of machine learning in different domains...},
  keywords={machine learning, applications, AI},
  year={2020}
}
```

**Output after fixing:**
```bibtex
@article{smith2020,
  title = {Machine Learning Applications in Modern Data Science},
  journal = {Journal of Machine Learning Research},
  year = {2020},
  author = {Smith, John and Doe, Jane},
  volume = {21},
  number = {15},
  pages = {1--25},
  doi = {10.1234/jmlr.2020.15.001}
}
```

### Example 2: DOI-based Enhancement

**Input:**
```bibtex
@article{incomplete2021,
  doi={10.1038/s41586-021-03819-2},
  title={Some title}
}
```

**Output:**
```bibtex
@article{incomplete2021,
  title = {Deep Learning Advances in Computer Vision},
  journal = {Nature},
  year = {2021},
  author = {Johnson, Alice and Brown, Bob},
  volume = {595},
  number = {7868},
  pages = {234--239},
  doi = {10.1038/s41586-021-03819-2}
}
```

### Example 3: Batch Processing

Process multiple files:
```bash
# Process all .bib files in current directory
for file in *.bib; do
    python bibtex_fixer_v4.py "$file" -e your.email@example.com
done
```

### Example 4: Large Bibliography Processing

For large bibliographies with many entries:
```bash
# Use more threads for faster processing
python bibtex_fixer_v4.py large_bibliography.bib -t 12 -e your.email@example.com -o cleaned_bibliography.bib
```

## How It Works

1. **Entry Analysis**: Each BibTeX entry is analyzed for available information (title, authors, DOI, journal)

2. **CrossRef Search**: The tool searches CrossRef using multiple strategies:
   - DOI lookup (highest priority)
   - Title-based search
   - Author + title combination search

3. **Match Validation**: Found matches are validated using:
   - Title similarity (fuzzy matching)
   - Journal name matching
   - Author consistency checks

4. **Data Merging**: Valid matches are merged with original entries:
   - Missing fields are added
   - Incomplete fields are enhanced
   - Formatting is cleaned and standardized

5. **Output Generation**: Clean BibTeX file is generated with:
   - Proper field ordering (title, journal, year, author, etc.)
   - Removed unwanted fields (abstract, keywords)
   - Consistent formatting

### CrossRef API Best Practices

- Always provide an email address with `-e` flag for better rate limits
- The tool automatically applies rate limiting (100ms between requests per thread)
- CrossRef allows up to 50 requests per second for identified users

## Troubleshooting

### Common Issues

1. **Rate Limiting**: If you encounter rate limiting, reduce thread count or add delays
2. **No Matches Found**: Some entries may not be in CrossRef database
3. **Journal Mismatch**: Tool is conservative about journal matching to avoid incorrect data

## Output Format

The tool ensures consistent output formatting:
- Proper BibTeX syntax with consistent indentation
- Clean field values without formatting artifacts
- Removed abstract and keywords fields for cleaner output

## Limitations

- Depends on CrossRef database coverage
- May not find matches for very recent publications
- Conservative matching may miss some valid entries
- Requires internet connection for CrossRef API access

## License

This tool is provided as-is for academic and research