import os

def list_files_and_folders(start_path, indent=0, exclude_dirs=None, include_files=None, include_subfolders=False):
    if exclude_dirs is None:
        exclude_dirs = {".git", "__pycache__",".venv", "Scripts", "ORM", "event", "_vendor", "events","botbuilder_env", "pkg_resources", "werkzeug", "sqlalchemy", "dialects"}  # Exclude non-code dirs
    
    if include_files is None:
        include_files = {".env", "requirements.txt", "Dockerfile", "Makefile"}  # Include only specific files
    
    try:
        for item in os.listdir(start_path):
            item_path = os.path.join(start_path, item)
            # Skip excluded directories
            if os.path.isdir(item_path) and item in exclude_dirs:
                continue
            # Include only Python files and specific dev files
            if os.path.isdir(item_path) or (os.path.isfile(item_path) and (item.endswith('.py') or item in include_files)):
                # Print the item with its relative indentation
                print('  ' * indent + f'├── {item}')
            
            # If the item is a directory and we need to include subfolders, recurse into it
            if os.path.isdir(item_path):
                if include_subfolders or item == 'app':  # Recurse only if it's app or required subfolders
                    list_files_and_folders(item_path, indent + 1, exclude_dirs, include_files, include_subfolders)
    except PermissionError as e:
        print(f"PermissionError: {e}")  # Handle permission errors gracefully

# Specify the path to your project root directory
project_root = os.getcwd()  # Get the current working directory
print(f"Project Structure for: {project_root}")
list_files_and_folders(project_root, include_subfolders=True)
