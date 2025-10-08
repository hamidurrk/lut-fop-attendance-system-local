import os
import argparse

def count_lines_in_file(file_path):
    """Count all lines in a file (including comments and documentation)."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        return len(lines)
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return 0

def count_lines_in_directory(directory, extensions=None, exclude_dirs=None):
    """Count lines of code in all files with specified extensions in a directory (recursive)."""
    if extensions is None:
        extensions = ['.py']  
    
    if exclude_dirs is None:
        exclude_dirs = ['.venv', 'env', '.git', '__pycache__', 'node_modules', 'data', 'media', 'output']
    
    total_lines = 0
    file_count = 0
    stats_by_dir = {}
    file_stats = []  
    
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        dir_lines = 0
        dir_files = 0
        
        for file in files:
            file_ext = os.path.splitext(file)[1].lower()
            if file_ext in extensions:
                file_path = os.path.join(root, file)
                lines = count_lines_in_file(file_path)
                
                rel_file_path = os.path.relpath(file_path, directory)
                file_stats.append((rel_file_path, lines))
                
                dir_lines += lines
                dir_files += 1
        
        if dir_files > 0:
            rel_path = os.path.relpath(root, directory)
            stats_by_dir[rel_path] = (dir_files, dir_lines)
            total_lines += dir_lines
            file_count += dir_files
    
    return total_lines, file_count, stats_by_dir, file_stats

def main():
    parser = argparse.ArgumentParser(description='Count lines of code in a project.')
    parser.add_argument('--dir', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        help='Project directory to scan (default: parent of script directory)')
    parser.add_argument('--extensions', default='.py', 
                        help='Comma-separated list of file extensions to count (default: .py)')
    parser.add_argument('--exclude', default='venv,env,.git,__pycache__,node_modules',
                        help='Comma-separated list of directories to exclude')
    parser.add_argument('--verbose', action='store_true', help='Print details for each file')
    
    args = parser.parse_args()
    
    project_dir = args.dir
    extensions = [ext.strip() for ext in args.extensions.split(',')]
    extensions = ['.' + ext if not ext.startswith('.') else ext for ext in extensions]
    exclude_dirs = ['.venv', 'env', '.git', '__pycache__', 'node_modules', 'data', 'media', 'output']
    
    print(f"Scanning directory: {project_dir}")
    print(f"File extensions: {', '.join(extensions)}")
    print(f"Excluding directories: {', '.join(exclude_dirs)}")
    print("Counting lines (including comments and documentation)...")
    
    total_lines, file_count, stats_by_dir, file_stats = count_lines_in_directory(
        project_dir, extensions, exclude_dirs)
    
    print("\n" + "="*80)
    print(f"Code Statistics for {', '.join(extensions)} Files (including comments and docs)")
    print("="*80)
    
    print("\nFile Statistics:")
    print("-"*80)
    print(f"{'File Path':<65} {'Lines':<10}")
    print("-"*80)
    
    sorted_files = sorted(file_stats, key=lambda x: x[1], reverse=True)
    for file_path, lines in sorted_files:
        print(f"{file_path:<65} {lines:<10}")
    
    print("\n\nDirectory Summary:")
    print("-"*80)
    print(f"{'Directory':<50} {'Files':<10} {'Lines':<10}")
    print("-"*80)
    
    sorted_dirs = sorted(stats_by_dir.items(), key=lambda x: x[1][1], reverse=True)
    for dir_name, (files, lines) in sorted_dirs:
        print(f"{dir_name:<50} {files:<10} {lines:<10}")
    
    print("-"*80)
    print(f"{'TOTAL':<50} {file_count:<10} {total_lines:<10}")
    print("="*80)

if __name__ == "__main__":
    main()