import re
from typing import List, Dict, Tuple
from backend.config.settings import settings


class DiffParser:
    
    # Patterns for noise files
    NOISE_PATTERNS = [
        r'\.lock$',
        r'package-lock\.json$',
        r'yarn\.lock$',
        r'pnpm-lock\.yaml$',
        r'\.min\.(js|css)$',
        r'node_modules/',
        r'\.git/',
        r'\.DS_Store$',
        r'\.log$',
        r'dist/',
        r'build/',
        r'\.pyc$',
        r'__pycache__/',
        r'\.png$',
        r'\.jpg$',
        r'\.jpeg$',
        r'\.gif$',
        r'\.svg$',
        r'\.ico$',
        r'\.woff',
        r'\.woff2$',
        r'\.ttf$',
        r'\.eot$',
    ]
    
    def __init__(self):
        self.noise_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.NOISE_PATTERNS]
    
    def is_noise_file(self, filepath: str) -> bool:
        """Check if a file should be filtered out as noise."""
        for pattern in self.noise_regex:
            if pattern.search(filepath):
                return True
        return False
    
    def parse_diff(self, diff_text: str) -> List[Dict[str, any]]:
        if not diff_text:
            return []
        
        files = []
        current_file = None
        current_lines = []
        
        lines = diff_text.split('\n')
        
        for line in lines:
            # File header: diff --git a/path b/path
            if line.startswith('diff --git'):
                if current_file:
                    current_file['content'] = '\n'.join(current_lines)
                    files.append(current_file)
                
                # Extract file paths
                match = re.match(r'diff --git a/(.+?) b/(.+?)$', line)
                if match:
                    old_path = match.group(1)
                    new_path = match.group(2)
                    current_file = {
                        'old_path': old_path,
                        'new_path': new_path,
                        'content': '',
                        'added_lines': 0,
                        'removed_lines': 0
                    }
                    current_lines = [line]
                continue
            
            # Index line: index hash1..hash2 mode
            if line.startswith('index '):
                if current_file:
                    current_lines.append(line)
                continue
            
            # Binary file indicator
            if line.startswith('Binary files'):
                if current_file:
                    current_file['is_binary'] = True
                    current_lines.append(line)
                continue
            
            # New file: new file mode
            if line.startswith('new file mode'):
                if current_file:
                    current_lines.append(line)
                continue
            
            # Deleted file: deleted file mode
            if line.startswith('deleted file mode'):
                if current_file:
                    current_file['is_deleted'] = True
                    current_lines.append(line)
                continue
            
            # Hunk header: @@ -start,count +start,count @@
            if line.startswith('@@'):
                if current_file:
                    current_lines.append(line)
                    # Parse hunk header for line counts
                    match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
                    if match:
                        removed = int(match.group(2) or 1)
                        added = int(match.group(4) or 1)
                        current_file['removed_lines'] += removed
                        current_file['added_lines'] += added
                continue
            
            # Diff content lines
            if current_file:
                current_lines.append(line)
                # Count added/removed lines
                if line.startswith('+') and not line.startswith('+++'):
                    current_file['added_lines'] += 1
                elif line.startswith('-') and not line.startswith('---'):
                    current_file['removed_lines'] += 1
        
        # Add last file
        if current_file:
            current_file['content'] = '\n'.join(current_lines)
            files.append(current_file)
        
        return files
    
    def filter_noise(self, files: List[Dict[str, any]]) -> List[Dict[str, any]]:
        filtered = []
        for file_info in files:
            filepath = file_info.get('new_path') or file_info.get('old_path', '')
            if not self.is_noise_file(filepath):
                filtered.append(file_info)
        return filtered
    
    def chunk_large_file(self, file_content: str, max_size: int = None) -> List[str]:
        if max_size is None:
            max_size = settings.max_file_size
        
        if len(file_content) <= max_size:
            return [file_content]
        
        chunks = []
        lines = file_content.split('\n')
        current_chunk = []
        current_size = 0
        
        for line in lines:
            line_size = len(line) + 1  # +1 for newline
            if current_size + line_size > max_size and current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = [line]
                current_size = line_size
            else:
                current_chunk.append(line)
                current_size += line_size
        
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        return chunks
    
    def process_diff(self, diff_text: str) -> Tuple[str, List[Dict[str, any]]]:
        # Check if diff is too large
        if len(diff_text) > settings.max_diff_size:
            # Truncate and add warning
            truncated = diff_text[:settings.max_diff_size]
            diff_text = truncated + f"\n\n[DIFF TRUNCATED: Original size {len(diff_text)} chars, max {settings.max_diff_size} chars]"
        
        # Parse diff
        files = self.parse_diff(diff_text)
        
        # Filter noise
        filtered_files = self.filter_noise(files)
        
        # Reconstruct filtered diff
        filtered_diff = '\n'.join([f['content'] for f in filtered_files])
        
        return filtered_diff, filtered_files
    
    def get_file_summary(self, files: List[Dict[str, any]]) -> str:
        summary_lines = []
        for file_info in files:
            filepath = file_info.get('new_path') or file_info.get('old_path', '')
            added = file_info.get('added_lines', 0)
            removed = file_info.get('removed_lines', 0)
            status = "modified"
            if file_info.get('is_deleted'):
                status = "deleted"
            elif file_info.get('is_binary'):
                status = "binary"
            elif not file_info.get('old_path'):
                status = "new"
            
            summary_lines.append(f"{status}: {filepath} (+{added}/-{removed})")
        
        return '\n'.join(summary_lines)


# Global diff parser instance
diff_parser = DiffParser()

