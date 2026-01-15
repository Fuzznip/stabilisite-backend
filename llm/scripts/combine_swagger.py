# filepath: d:\dev\stability-backend-prototypes\combine_swagger.py
import json
import os

def combine_swagger_files(input_directory, output_file):
    """
    Combine multiple swagger JSON files into a single swagger.json file
    
    Args:
        input_directory: Directory containing swagger component files
        output_file: Path to the output combined swagger file
    """
    base_file = os.path.join(input_directory, "base.json")
    
    # Ensure the input directory exists
    if not os.path.exists(input_directory):
        os.makedirs(input_directory)
        print(f"Created directory: {input_directory}")
    
    # Load base swagger file
    try:
        with open(base_file, "r") as base:
            swagger = json.load(base)
    except FileNotFoundError:
        print(f"Base file not found: {base_file}")
        return
    
    # Ensure the base swagger has paths and components
    if "paths" not in swagger:
        swagger["paths"] = {}
    if "components" not in swagger:
        swagger["components"] = {}
    if "schemas" not in swagger.get("components", {}):
        swagger["components"]["schemas"] = {}
    
    # Combine all other swagger files
    for filename in os.listdir(input_directory):
        if filename != "base.json" and filename.endswith(".json"):
            file_path = os.path.join(input_directory, filename)
            try:
                with open(file_path, "r") as f:
                    partial = json.load(f)
                    
                    # Update paths
                    if "paths" in partial:
                        swagger["paths"].update(partial["paths"])
                    
                    # Update schemas
                    if "components" in partial and "schemas" in partial["components"]:
                        swagger["components"]["schemas"].update(partial["components"]["schemas"])
                        
                    print(f"Processed: {filename}")
            except json.JSONDecodeError:
                print(f"Invalid JSON in file: {filename}")
            except Exception as e:
                print(f"Error processing file {filename}: {str(e)}")
    
    # Ensure output directory exists
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")
    
    # Write the combined swagger file
    with open(output_file, "w") as output:
        json.dump(swagger, output, indent=2)
    
    print(f"Successfully created combined swagger file: {output_file}")

if __name__ == "__main__":
    # Define the input directory and output file
    input_dir = "static/swagger"
    output_file = "static/swagger.json"
    
    # Get absolute paths based on the project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_input_dir = os.path.join(project_root, input_dir)
    abs_output_file = os.path.join(project_root, output_file)
    
    combine_swagger_files(abs_input_dir, abs_output_file)
    