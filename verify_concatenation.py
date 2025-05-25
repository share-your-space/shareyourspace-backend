import os

def verify_concatenation(directory, concatenated_file, script_to_exclude):
    """
    Verifies that all expected files in a directory are present in the concatenated file.

    Args:
        directory (str): The path to the directory that was concatenated.
        concatenated_file (str): The path to the concatenated output file.
        script_to_exclude (str): The name of the script that generated the concatenated file.
    """
    print(f"Verifying contents of: {concatenated_file}")
    print(f"Based on files in: {os.path.abspath(directory)}\n")

    excluded_dirs = ['.git']
    # also exclude the concatenated file itself and the script that generated it
    # and the verification script itself
    excluded_files = [os.path.basename(concatenated_file), os.path.basename(script_to_exclude), os.path.basename(__file__)]

    expected_files_relative_paths = set()
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in excluded_dirs]
        for filename in files:
            if filename not in excluded_files:
                filepath = os.path.join(root, filename)
                relative_filepath = os.path.relpath(filepath, directory)
                expected_files_relative_paths.add(relative_filepath)

    if not expected_files_relative_paths:
        print("No files found in the directory to verify (after exclusions).")
        return

    print(f"Found {len(expected_files_relative_paths)} expected files in the directory (after exclusions).")

    try:
        with open(concatenated_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: The concatenated file '{concatenated_file}' was not found.")
        return
    
    missing_in_txt = []
    found_in_txt_count = 0

    for rel_path in sorted(list(expected_files_relative_paths)):
        search_string = f"--- START OF FILE: {rel_path} ---"
        if search_string not in content:
            missing_in_txt.append(rel_path)
        else:
            found_in_txt_count += 1
            
    print(f"\n--- Verification Results ---")
    if not missing_in_txt:
        print(f"Success! All {len(expected_files_relative_paths)} expected files appear to be included in '{concatenated_file}'.")
        if found_in_txt_count == len(expected_files_relative_paths):
            print("The count of 'START OF FILE' markers matches the number of expected files.")
        else:
            print(f"Warning: Number of 'START OF FILE' markers ({found_in_txt_count}) does not match expected files ({len(expected_files_relative_paths)}).")
            print("This could indicate duplicate entries or other inconsistencies.")

    else:
        print(f"Error: The following {len(missing_in_txt)} files from the directory seem to be MISSING from '{concatenated_file}':")
        for item in missing_in_txt:
            print(f"  - {item}")
        print(f"\nFound {found_in_txt_count} out of {len(expected_files_relative_paths)} expected files in the .txt file.")

if __name__ == "__main__":
    current_directory = "."
    output_file = "backend_content.txt"
    concatenation_script = "concatenate_backend_files.py"
    verify_concatenation(current_directory, output_file, concatenation_script) 