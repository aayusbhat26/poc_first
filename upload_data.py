import os
import time
from azure.core.exceptions import HttpResponseError
from azure.storage.filedatalake import DataLakeServiceClient

# --- Configuration ---
# Note: For production pipelines, it's best to fetch this from Azure Key Vault or Environment Variables!
CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=straccprojectnag;AccountKey=YOUR_ACCOUNT_KEY;EndpointSuffix=core.windows.net"
CONTAINER_NAME = "landing"
LOCAL_SOURCE_FOLDER = "./ev_data_output/ev_telemetry" 
DESTINATION_FOLDER = "ev_telemetry" 

def upload_local_directory_to_adls():
    try:
        service_client = DataLakeServiceClient.from_connection_string(CONNECTION_STRING)
        file_system_client = service_client.get_file_system_client(CONTAINER_NAME)
        
        for root, dirs, files in os.walk(LOCAL_SOURCE_FOLDER):
            
            # --- HIGH-SPEED FILTERING ---
            # Updated to 20260101 to match the new multi-year batch generator output
            if os.path.abspath(root) == os.path.abspath(LOCAL_SOURCE_FOLDER):
                dirs.sort() # Ensure chronological order
                dirs[:] = [d for d in dirs if d >= "20260101"]
            
            for file_name in files:
                local_file_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(local_file_path, LOCAL_SOURCE_FOLDER)
                adls_path = f"{DESTINATION_FOLDER}/{relative_path.replace(os.sep, '/')}"
                
                file_client = file_system_client.get_file_client(adls_path)
                
                print(f"Uploading: {adls_path}...", end=" ", flush=True)
                
                with open(local_file_path, "rb") as file_data:
                    file_contents = file_data.read()
                    try:
                        # Attempt the normal upload
                        file_client.upload_data(file_contents, overwrite=True)
                        print("Success!")
                        
                    except HttpResponseError as e:
                        # AUTO-UNLOCK: Handle the ConditionNotMet lock
                        if "ConditionNotMet" in str(e) or e.status_code == 412:
                            print("\n  -> Lock detected. Forcing delete and retry...", end=" ", flush=True)
                            file_client.delete_file()  
                            time.sleep(1)              
                            file_client.upload_data(file_contents, overwrite=True)
                            print("Success!")
                        else:
                            raise e
                            
        print("\n✅ All files uploaded successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during upload: {e}")

if __name__ == "__main__":
    upload_local_directory_to_adls()