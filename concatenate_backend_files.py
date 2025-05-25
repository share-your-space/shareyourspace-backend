import os

def generate_tree_structure(directory, excluded_dirs, excluded_files):
    """
    Generates a string representation of the directory tree structure.

    Args:
        directory (str): The path to the directory.
        excluded_dirs (list): A list of directory names to exclude.
        excluded_files (list): A list of file names to exclude.
    Returns:
        str: The string representation of the directory tree.
    """
    tree_lines = [f"Directory Tree for: {os.path.abspath(directory)}\n"]
    for root, dirs, files in os.walk(directory, topdown=True):
        # Filter out excluded directories
        dirs[:] = [d for d in dirs if d not in excluded_dirs]
        
        level = root.replace(directory, '').count(os.sep)
        indent = '    ' * level
        tree_lines.append(f"{indent}├── {os.path.basename(root)}/")
        sub_indent = '    ' * (level + 1)
        for f in files:
            if f not in excluded_files:
                tree_lines.append(f"{sub_indent}├── {f}")
    return "\n".join(tree_lines) + "\n\n"

def concatenate_files(directory, output_file):
    """
    Concatenates the content of all files in a directory into a single output file,
    prepending it with the directory tree structure.

    Args:
        directory (str): The path to the directory.
        output_file (str): The path to the output file.
    """
    excluded_dirs = ['.git']
    # Add the output file itself to excluded_files to prevent it from being included in the tree or content
    script_name = os.path.basename(__file__)
    output_file_name = os.path.basename(output_file)
    excluded_files = [script_name, output_file_name, "verify_concatenation.py"]

    with open(output_file, 'w', encoding='utf-8', errors='ignore') as outfile:
        # Generate and write the tree structure first
        tree_structure = generate_tree_structure(directory, excluded_dirs, excluded_files + [output_file_name]) # ensure output file is not in tree
        outfile.write("--- DIRECTORY TREE ---\n\n")
        outfile.write(tree_structure)
        outfile.write("=" * 80 + "\n\n")

        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in excluded_dirs]

            for filename in files:
                if filename in excluded_files:
                    continue

                filepath = os.path.join(root, filename)
                relative_filepath = os.path.relpath(filepath, directory)
                
                outfile.write(f"--- START OF FILE: {relative_filepath} ---\n\n")
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as infile:
                        outfile.write(infile.read())
                    outfile.write(f"\n\n--- END OF FILE: {relative_filepath} ---\n\n")
                    outfile.write("=" * 80 + "\n\n")
                except Exception as e:
                    outfile.write(f"Error reading file {relative_filepath}: {e}\n")
                    outfile.write(f"\n\n--- END OF FILE: {relative_filepath} (with error) ---\n\n")
                    outfile.write("=" * 80 + "\n\n")

if __name__ == "__main__":
    backend_directory = "."
    output_filename = "backend_content.txt"
    output_filepath = os.path.join(backend_directory, output_filename)

    concatenate_files(backend_directory, output_filepath)
    print(f"All files in '{backend_directory}' (with directory tree) have been concatenated into '{output_filepath}'") 