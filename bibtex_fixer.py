#!/usr/bin/env python3
"""
BibTeX Fixer using CrossRef API
Fixes missing information and corrects errors in BibTeX entries
"""

import requests
import re
import json
import time
import argparse
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote
import bibtexparser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bparser import BibTexParser
from bibtexparser.bibdatabase import BibDatabase
from fuzzywuzzy import fuzz
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import threading


class CrossRefAPI:
    """Handle interactions with CrossRef API with thread safety"""
    
    def __init__(self, email: str = None):
        self.base_url = "https://api.crossref.org/works"
        self.email = email
        self.session = requests.Session()
        if email:
            self.session.headers.update({'User-Agent': f'BibTeXFixer/1.0 (mailto:{email})'})
        # Thread-local storage for rate limiting
        self._local = threading.local()
    
    def _rate_limit(self):
        """Apply rate limiting per thread"""
        if not hasattr(self._local, 'last_request'):
            self._local.last_request = 0
        
        current_time = time.time()
        time_since_last = current_time - self._local.last_request
        min_interval = 0.1  # 100ms between requests per thread
        
        if time_since_last < min_interval:
            time.sleep(min_interval - time_since_last)
        
        self._local.last_request = time.time()
    
    def search_by_title(self, title: str, rows: int = 5) -> List[Dict]:
        """Search CrossRef by title"""
        self._rate_limit()
        
        params = {
            'query.title': title,
            'rows': rows,
            'sort': 'relevance'
        }
        
        try:
            response = self.session.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('message', {}).get('items', [])
        except requests.exceptions.RequestException as e:
            print(f"Error searching by title '{title}': {e}")
            return []
    
    def search_by_doi(self, doi: str) -> Optional[Dict]:
        """Search CrossRef by DOI"""
        self._rate_limit()
        
        clean_doi = doi.replace('https://doi.org/', '').replace('http://dx.doi.org/', '')
        url = f"{self.base_url}/{clean_doi}"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get('message', {})
        except requests.exceptions.RequestException as e:
            print(f"Error searching by DOI '{doi}': {e}")
            return None
    
    def search_by_author_title(self, authors: List[str], title: str) -> List[Dict]:
        """Search CrossRef by author and title combination"""
        self._rate_limit()
        
        author_query = ' '.join(authors[:2])  # Use first two authors
        params = {
            'query.author': author_query,
            'query.title': title,
            'rows': 3,
            'sort': 'relevance'
        }
        
        try:
            response = self.session.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('message', {}).get('items', [])
        except requests.exceptions.RequestException as e:
            print(f"Error searching by author+title: {e}")
            return []


class BibTeXFixer:
    """Main class for fixing BibTeX entries with parallel processing"""
    
    def __init__(self, email: str = None, max_workers: int = 6):
        self.crossref = CrossRefAPI(email)
        self.parser = BibTexParser()
        self.parser.ignore_nonstandard_types = False
        self.parser.homogenise_fields = True  # Standardize field names
        self.writer = BibTexWriter()
        self.writer.indent = '  '
        self.writer.align_values = True
        self.writer.add_trailing_comma = False  # Prevent trailing commas
        self.writer.common_strings = []  # Avoid string substitutions
        self.max_workers = max_workers
        self.print_lock = Lock()  # For thread-safe printing
        
    def load_bib_file(self, filename: str) -> BibDatabase:
        """Load BibTeX file"""
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                return bibtexparser.load(file, parser=self.parser)
        except Exception as e:
            print(f"Error loading file {filename}: {e}")
            return BibDatabase()
    
    def thread_safe_print(self, message: str):
        """Thread-safe printing"""
        with self.print_lock:
            print(message)
    
    def save_bib_file(self, database: BibDatabase, filename: str):
        """Save BibTeX file"""
        try:
            # Filter out empty comments before saving
            if hasattr(database, 'comments'):
                database.comments = [comment for comment in database.comments if comment.strip()]
            
            # Filter out entries with missing required fields
            valid_entries = []
            for entry in database.entries:
                # Check if entry has required fields
                if entry.get('ID') and entry.get('ENTRYTYPE'):
                    valid_entries.append(entry)
                else:
                    self.thread_safe_print(f"Warning: Skipping invalid entry: {entry}")
            
            database.entries = valid_entries
            
            with open(filename, 'w', encoding='utf-8') as file:
                bibtexparser.dump(database, file, writer=self.writer)
        except Exception as e:
            print(f"Error saving file {filename}: {e}")
    
    def extract_authors(self, entry: Dict) -> List[str]:
        """Extract author names from BibTeX entry"""
        authors = []
        if 'author' in entry:
            # Simple author extraction - can be improved
            author_string = entry['author']
            authors = [name.strip() for name in author_string.replace(' and ', ',').split(',')]
        return authors
    
    def clean_title(self, title: str) -> str:
        """Clean title by removing extra formatting and unwanted characters"""
        if not title:
            return title
        
        # Remove HTML tags
        title = re.sub(r'<[^>]+>', '', title)
        
        # Remove extra whitespace and normalize spaces
        title = re.sub(r'\s+', ' ', title).strip()
        
        # Remove trailing periods if they exist
        title = title.rstrip('.')
        
        # Remove common formatting artifacts
        title = title.replace('&amp;', '&')
        title = title.replace('&lt;', '<')
        title = title.replace('&gt;', '>')
        title = title.replace('&quot;', '"')
        title = title.replace('&#39;', "'")
        title = title.replace('&nbsp;', ' ')
        
        # Remove excessive punctuation
        title = re.sub(r'[.]{2,}', '.', title)  # Multiple periods
        title = re.sub(r'[,]{2,}', ',', title)  # Multiple commas
        title = re.sub(r'[;]{2,}', ';', title)  # Multiple semicolons
        
        # Remove leading/trailing quotes if they wrap the entire title
        if (title.startswith('"') and title.endswith('"')) or \
           (title.startswith("'") and title.endswith("'")):
            title = title[1:-1]
        
        # Remove common prefixes that shouldn't be in titles
        prefixes_to_remove = [
            'Title: ', 'TITLE: ', 'title: ',
            'Article: ', 'ARTICLE: ', 'article: '
        ]
        for prefix in prefixes_to_remove:
            if title.startswith(prefix):
                title = title[len(prefix):]
                break
        
        return title.strip()
    
    def crossref_to_bibtex(self, crossref_item: Dict) -> Dict:
        """Convert CrossRef item to BibTeX format"""
        entry = {}
        
        # Title
        if 'title' in crossref_item and crossref_item['title']:
            raw_title = crossref_item['title'][0]
            entry['title'] = self.clean_title(raw_title)
        
        # Authors
        if 'author' in crossref_item:
            authors = []
            for author in crossref_item['author']:
                if 'given' in author and 'family' in author:
                    authors.append(f"{author['family']}, {author['given']}")
                elif 'family' in author:
                    authors.append(author['family'])
            if authors:
                entry['author'] = ' and '.join(authors)
        
        # Journal
        if 'container-title' in crossref_item and crossref_item['container-title']:
            raw_journal = crossref_item['container-title'][0]
            entry['journal'] = self.clean_title(raw_journal)
        
        # Year and Month
        year = None
        month = None
        
        # Try different date fields in order of preference
        date_fields = ['published-print', 'published-online', 'created', 'issued']
        for date_field in date_fields:
            if date_field in crossref_item and crossref_item[date_field]:
                date_parts = crossref_item[date_field].get('date-parts', [[]])[0]
                if date_parts:
                    if len(date_parts) >= 1 and date_parts[0]:
                        year = str(date_parts[0])
                    if len(date_parts) >= 2 and date_parts[1]:
                        month_num = date_parts[1]
                        # Convert month number to name
                        month_names = {
                            1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr',
                            5: 'may', 6: 'jun', 7: 'jul', 8: 'aug',
                            9: 'sep', 10: 'oct', 11: 'nov', 12: 'dec'
                        }
                        month = month_names.get(month_num, str(month_num))
                    break
        
        if year:
            entry['year'] = year
        if month:
            entry['month'] = month
        
        # Volume - handle both string and number formats
        if 'volume' in crossref_item and crossref_item['volume']:
            entry['volume'] = str(crossref_item['volume']).strip()
        
        # Issue/Number - try multiple field names
        number_fields = ['issue', 'journal-issue', 'number']
        for field in number_fields:
            if field in crossref_item and crossref_item[field]:
                if isinstance(crossref_item[field], dict):
                    # Handle nested issue structure
                    if 'issue' in crossref_item[field]:
                        entry['number'] = str(crossref_item[field]['issue']).strip()
                        break
                else:
                    entry['number'] = str(crossref_item[field]).strip()
                    break
        
        # Pages - handle various formats
        if 'page' in crossref_item and crossref_item['page']:
            pages = crossref_item['page'].strip()
            # Normalize page ranges
            pages = re.sub(r'[-−–—]+', '--', pages)  # Replace various dashes with standard range
            entry['pages'] = pages
        elif 'article-number' in crossref_item and crossref_item['article-number']:
            # Some journals use article numbers instead of pages
            entry['pages'] = crossref_item['article-number']
        
        # DOI
        if 'DOI' in crossref_item:
            entry['doi'] = crossref_item['DOI']
        
        # Publisher - handle various publisher fields
        publisher_fields = ['publisher', 'institution', 'school']
        for field in publisher_fields:
            if field in crossref_item and crossref_item[field]:
                if isinstance(crossref_item[field], list):
                    entry['publisher'] = crossref_item[field][0]
                else:
                    entry['publisher'] = str(crossref_item[field]).strip()
                break
        
        # Additional fields for different entry types
        
        # Book title for chapters/sections
        if 'container-title' in crossref_item and crossref_item['container-title']:
            container_title = self.clean_title(crossref_item['container-title'][0])
            entry_type = crossref_item.get('type', '')
            
            if entry_type in ['book-chapter', 'book-section']:
                entry['booktitle'] = container_title
            elif entry_type not in ['journal-article']:
                # For proceedings, etc.
                entry['booktitle'] = container_title
        
        # ISBN for books
        if 'ISBN' in crossref_item and crossref_item['ISBN']:
            entry['isbn'] = crossref_item['ISBN'][0] if isinstance(crossref_item['ISBN'], list) else crossref_item['ISBN']
        
        # ISSN for journals
        if 'ISSN' in crossref_item and crossref_item['ISSN']:
            entry['issn'] = crossref_item['ISSN'][0] if isinstance(crossref_item['ISSN'], list) else crossref_item['ISSN']
        
        # URL if available
        if 'URL' in crossref_item and crossref_item['URL']:
            entry['url'] = crossref_item['URL']
        
        # Note: Abstract is intentionally excluded - we don't fetch it from CrossRef
        
        # Entry type
        entry_type = crossref_item.get('type', 'article')
        if entry_type == 'journal-article':
            entry['ENTRYTYPE'] = 'article'
        elif entry_type == 'book':
            entry['ENTRYTYPE'] = 'book'
        elif entry_type in ['book-chapter', 'book-section']:
            entry['ENTRYTYPE'] = 'inbook'
        elif entry_type == 'proceedings-article':
            entry['ENTRYTYPE'] = 'inproceedings'
        else:
            entry['ENTRYTYPE'] = 'article'
        
        return entry
    
    def calculate_similarity(self, entry1: Dict, entry2: Dict) -> float:
        """Calculate similarity between two entries"""
        title1 = self.clean_title(entry1.get('title', '')).lower()
        title2 = self.clean_title(entry2.get('title', '')).lower()
        
        if not title1 or not title2:
            return 0.0
        
        return fuzz.ratio(title1, title2) / 100.0
    
    def find_best_match(self, entry: Dict, candidates: List[Dict]) -> Optional[Dict]:
        """Find best matching candidate from CrossRef results"""
        if not candidates:
            return None
        
        best_match = None
        best_score = 0.0
        original_journal = self.clean_title(entry.get('journal', '')).lower()
        
        for candidate in candidates:
            crossref_entry = self.crossref_to_bibtex(candidate)
            
            # Check journal match first if original has a journal
            if original_journal:
                crossref_journal = self.clean_title(crossref_entry.get('journal', '')).lower()
                if not crossref_journal:
                    # Skip if CrossRef entry has no journal when original does
                    continue
                
                # Calculate journal similarity
                journal_similarity = fuzz.ratio(original_journal, crossref_journal) / 100.0
                if journal_similarity < 0.8:  # Require high journal similarity
                    # self.thread_safe_print(f"  Skipping match - journal mismatch: '{original_journal}' vs '{crossref_journal}'")
                    continue
            
            # Calculate title similarity
            title_similarity = self.calculate_similarity(entry, crossref_entry)
            
            if title_similarity > best_score and title_similarity > 0.7:  # Threshold for matching
                best_score = title_similarity
                best_match = candidate
        
        if best_match:
            crossref_entry = self.crossref_to_bibtex(best_match)
            matched_journal = crossref_entry.get('journal', 'Unknown')
            self.thread_safe_print(f"  Found valid match from journal: {matched_journal}")
        
        return best_match
    
    def merge_entries(self, original: Dict, crossref_data: Dict) -> Dict:
        """Merge original entry with CrossRef data"""
        merged = original.copy()
        crossref_entry = self.crossref_to_bibtex(crossref_data)
        
        # Remove abstract and keywords from original entry
        if 'abstract' in merged:
            del merged['abstract']
            self.thread_safe_print(f"  Removed abstract")
        
        if 'keywords' in merged:
            del merged['keywords']
            self.thread_safe_print(f"  Removed keywords")
        
        # Define fields to update/add (removed abstract from the list)
        important_fields = ['title', 'author', 'journal', 'booktitle', 'year', 'month', 
                          'volume', 'number', 'pages', 'doi', 'publisher', 'isbn', 
                          'issn', 'url']
        
        for field in important_fields:
            if field in crossref_entry:
                if field not in merged or not merged[field].strip():
                    # Add missing field
                    merged[field] = crossref_entry[field]
                    self.thread_safe_print(f"  Added {field}: {crossref_entry[field]}")
                elif field == 'title':
                    # Always clean and potentially update title
                    original_clean = self.clean_title(merged[field])
                    crossref_clean = crossref_entry[field]  # Already cleaned in crossref_to_bibtex
                    
                    if len(crossref_clean) > len(original_clean) or \
                       (len(crossref_clean) >= len(original_clean) * 0.9 and 
                        self.clean_title(crossref_clean) != original_clean):
                        merged[field] = crossref_clean
                        self.thread_safe_print(f"  Updated {field}: {crossref_clean}")
                elif field == 'journal':
                    # Clean and update journal name if necessary
                    if len(crossref_entry[field]) > len(merged[field]):
                        merged[field] = crossref_entry[field]  # Already cleaned
                        self.thread_safe_print(f"  Updated {field}: {crossref_entry[field]}")
                elif field == 'pages':
                    # Update pages if current entry is missing or incomplete
                    current_pages = merged.get(field, '').strip()
                    new_pages = crossref_entry[field].strip()
                    if not current_pages or len(new_pages) > len(current_pages):
                        merged[field] = new_pages
                        self.thread_safe_print(f"  Updated {field}: {new_pages}")
                elif field in ['volume', 'number', 'year', 'month']:
                    # For numeric/short fields, prefer CrossRef data if original is missing
                    current_value = merged.get(field, '').strip()
                    if not current_value:
                        merged[field] = crossref_entry[field]
                        self.thread_safe_print(f"  Added {field}: {crossref_entry[field]}")
                elif field in ['isbn', 'issn', 'url']:
                    # Add supplementary fields if missing
                    if field not in merged or not merged[field].strip():
                        merged[field] = crossref_entry[field]
                        self.thread_safe_print(f"  Added {field}: {crossref_entry[field]}")
        
        return merged
    
    def fix_entry(self, entry_data: Tuple[int, Dict]) -> Tuple[int, Dict, bool]:
        """Fix a single BibTeX entry (modified for parallel processing)"""
        index, entry = entry_data
        entry_id = entry.get('ID', f'Entry_{index}')
        self.thread_safe_print(f"[Thread {threading.current_thread().name}] Processing entry {index}: {entry_id}")
        
        fixed = False
        
        # Always remove abstract and keywords if they exist, regardless of whether we find a match
        removed_fields = []
        if 'abstract' in entry:
            del entry['abstract']
            removed_fields.append('abstract')
        
        if 'keywords' in entry:
            del entry['keywords']
            removed_fields.append('keywords')
        
        if removed_fields:
            self.thread_safe_print(f"  Removed fields: {', '.join(removed_fields)}")
            fixed = True  # Mark as fixed if we removed unwanted fields
        
        # Try DOI first if available
        if 'doi' in entry and entry['doi']:
            self.thread_safe_print(f"  Searching by DOI: {entry['doi']}")
            crossref_data = self.crossref.search_by_doi(entry['doi'])
            if crossref_data:
                # For DOI matches, we're more lenient about journal matching
                # since DOI should be unique and authoritative
                entry = self.merge_entries(entry, crossref_data)
                fixed = True
                return index, entry, fixed
        
        # Try title search
        if 'title' in entry and entry['title']:
            self.thread_safe_print(f"  Searching by title: {entry['title'][:50]}...")
            candidates = self.crossref.search_by_title(entry['title'])
            best_match = self.find_best_match(entry, candidates)
            
            if best_match:
                entry = self.merge_entries(entry, best_match)
                fixed = True
                return index, entry, fixed
        
        # Try author + title search
        authors = self.extract_authors(entry)
        if authors and 'title' in entry:
            self.thread_safe_print(f"  Searching by author+title...")
            candidates = self.crossref.search_by_author_title(authors, entry['title'])
            best_match = self.find_best_match(entry, candidates)
            
            if best_match:
                entry = self.merge_entries(entry, best_match)
                fixed = True
        
        return index, entry, fixed
    
    def fix_bibliography(self, input_file: str, output_file: str = None):
        """Fix entire bibliography file using parallel processing"""
        if output_file is None:
            output_file = input_file.replace('.bib', '_fixed.bib')
        
        print(f"Loading bibliography from {input_file}")
        database = self.load_bib_file(input_file)
        
        if not database.entries:
            print("No entries found in the file")
            return
        
        print(f"Found {len(database.entries)} entries")
        print(f"Processing with {self.max_workers} threads...")
        
        # Prepare entries with indices for parallel processing
        indexed_entries = [(i, entry) for i, entry in enumerate(database.entries)]
        
        # Results storage
        results = {}
        fixed_count = 0
        completed_count = 0
        
        # Process entries in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_index = {
                executor.submit(self.fix_entry, entry_data): entry_data[0] 
                for entry_data in indexed_entries
            }
            
            # Process completed tasks
            for future in as_completed(future_to_index):
                try:
                    index, fixed_entry, was_fixed = future.result()
                    results[index] = (fixed_entry, was_fixed)
                    
                    if was_fixed:
                        fixed_count += 1
                    
                    completed_count += 1
                    
                    if completed_count % 10 == 0 or completed_count == len(database.entries):
                        print(f"Progress: {completed_count}/{len(database.entries)} entries processed")
                        
                except Exception as e:
                    index = future_to_index[future]
                    print(f"Error processing entry {index}: {e}")
                    # Keep original entry if processing failed
                    results[index] = (database.entries[index], False)
        
        # Update database with results in correct order
        for i in range(len(database.entries)):
            if i in results:
                database.entries[i] = results[i][0]
        
        print(f"\nCompleted! Fixed {fixed_count} out of {len(database.entries)} entries")
        print(f"Saving to {output_file}")
        self.save_bib_file(database, output_file)


def main():
    parser = argparse.ArgumentParser(description='Fix BibTeX entries using CrossRef API with parallel processing')
    parser.add_argument('input_file', help='Input BibTeX file')
    parser.add_argument('-o', '--output', help='Output file (default: input_file_fixed.bib)')
    parser.add_argument('-e', '--email', help='Email for CrossRef API (recommended)')
    parser.add_argument('-t', '--threads', type=int, default=6, 
                       help='Number of threads for parallel processing (default: 6)')
    parser.add_argument('--max-workers', type=int, help='Alias for --threads')
    
    args = parser.parse_args()
    
    # Use max_workers if provided, otherwise use threads
    max_workers = args.max_workers if args.max_workers is not None else args.threads
    
    # Validate thread count
    if max_workers < 1:
        print("Error: Number of threads must be at least 1")
        return
    elif max_workers > 20:
        print("Warning: Using more than 20 threads may hit API rate limits")
        max_workers = 20
    
    print(f"Starting BibTeX fixer with {max_workers} threads")
    fixer = BibTeXFixer(email=args.email, max_workers=max_workers)
    fixer.fix_bibliography(args.input_file, args.output)


if __name__ == "__main__":
    main()
