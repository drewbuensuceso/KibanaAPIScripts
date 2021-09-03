from botocore.retries import bucket
from requests.models import HTTPBasicAuth
from botocore.exceptions import NoCredentialsError
from datetime import datetime, timezone, timedelta
import requests, gzip, time, os, sys, threading, shutil, argparse, boto3, re

class KibanaApiManager():
    class Export(object):
        def __init__(self, base_url, username, password):
            self.url = base_url+"_export"
            self.username = username
            self.password = password
        
        def ExportSavedObjs(self, headers=None, data=None):
            headers = {'kbn-xsrf': 'true', 'Content-Type': 'application/json'} if headers==None else headers
            data = {"type": "index-pattern"} if data== None else data
            try:
                response = requests.post(url=self.url, json=data, headers=headers, auth=HTTPBasicAuth(username=self.username, password=self.password))
                print(response)
                if str(response) == f"<Response [200]>": ## only export when status code 200
                    timestamp = int(time.time())
                    filename = f"dash-export-{timestamp}.ndjson.gz"
                    with gzip.open(filename=f"{filename}", mode="wt") as gzipfile:
                        gzipfile.write(response.text)
                    return {"fileName": filename, "message": "Sucessfully Exported "}
                else:
                    print(f"Kibana export failed: Status Code: {response.json().get('statusCode')} {response.json().get('message')}")
                    return False
            except:
                print(f"message: There was an error exporting saved objects: {response.json().get('statusCode')}: " + response.json().get('message'))
                return False


    class Import(object):
        def __init__(self, base_url, username, password):
            self.url = base_url+"_import"
            self.username = username
            self.password = password
        
        def ImportDownloadedObjs(self, FileName, domain, headers=None):
            headers = {'kbn-xsrf': 'true'} if headers==None else headers
            with gzip.open(f"{FileName}", 'r') as f_in, open(f"{FileName}"[:-3], 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
                f_in.close()
                f_out.close()
            
            with open(f"{FileName}"[:-3]) as f:
                processed_text=f.read().replace('console.threatdefence.io', domain) ## Arg
                f.close()

            with open(f"{FileName}"[:-3], "w") as f:
                f.write(processed_text)
                f.close()

            file = {'file': open(f"{FileName}"[:-3], "r+")}
            response = requests.post(url=self.url, headers=headers, files=file, auth=HTTPBasicAuth(username=self.username, password=self.password),verify=False)
            os.remove(f"{FileName}"[:-3])
            os.remove(f"{FileName}")
            
            if str(response) == f"<Response [200]>":
                print(f"Imported {FileName} successfully!: {response}")
                 #write to registry
                with open("local_registry.txt", "a+") as file_object:
                    file_object.seek(0)
                    data = file_object.read(100)
                    if (len(data) > 0):
                        file_object.write("\n")
                        file_object.write(f"{FileName}")
                    elif len(data) == 0:
                        file_object.write(f"{FileName}")
                return True
            else:
                print(f"Kibana import failed: Status Code: {response.json().get('statusCode')} {response.json().get('message')}")
                return False

class ProgressPercentage(object):
        def __init__(self, filename):
            self._filename = filename
            self._size = float(os.path.getsize(filename))
            self._seen_so_far = 0
            self._lock = threading.Lock()

        def __call__(self, bytes_amount):
            # Progress bar for uploading single file to AWS
            with self._lock:
                self._seen_so_far += bytes_amount
                percentage = (self._seen_so_far / self._size) * 100
                sys.stdout.write(
                    "\r%s  %s / %s  (%.2f%%)" % (
                        self._filename, self._seen_so_far, self._size,
                        percentage))
                sys.stdout.flush()

class AWSManager(object):
    def __init__(self, access_key, secret_key):
        self.access_key = access_key
        self.secret_key = secret_key

    def ListBucketObjects(self, bucket, Prefix='dash-export'):
        s3 = boto3.client('s3', aws_access_key_id=self.access_key,
                        aws_secret_access_key=self.secret_key)
        response = s3.list_objects(Bucket=bucket,
                           MaxKeys=1000, 
                           Prefix=Prefix)
        object_list = response["Contents"]
        return(object_list)
    
    def DeleteOlderExports(self, bucket, Prefix='dash-export'):
        s3 = boto3.client('s3', aws_access_key_id=self.access_key,
                        aws_secret_access_key=self.secret_key)
        response = s3.list_objects(Bucket=bucket,
                           MaxKeys=10, 
                           Prefix=Prefix)
        current_date = datetime.now() - timedelta(days=7)
        #delete if object from bucket if 7 days or older
        try:
            keys_to_delete = [{'Key': object['Key']} for object in response['Contents'] if object['LastModified'] <= current_date.replace(tzinfo=timezone.utc)]
            s3.delete_objects(Bucket='my-bucket', Delete={'Objects': keys_to_delete})
        except:
            print("No files older than 7 days")

    def UploadToAws(self, local_file, bucket):
        s3 = boto3.client('s3', aws_access_key_id=self.access_key,
                        aws_secret_access_key=self.secret_key)

        try:
            s3.upload_file(local_file, bucket, Callback=ProgressPercentage(local_file), Key=local_file)
            os.remove(local_file) #delete file after upload
            print(f"Successfully Uploaded {local_file} to s3")
            return True
        except FileNotFoundError:
            print("The file was not found")
            return False
        except NoCredentialsError:
            print("Credentials not available")
            return False
        
    def DownloadFromAws(self, S3File, bucket):
        s3 = boto3.client('s3', aws_access_key_id=self.access_key,
                        aws_secret_access_key=self.secret_key)
        try:
            s3.download_file(bucket, S3File , S3File)
            print(f"Downloaded latest file!: {S3File}")
            return True
        except FileNotFoundError:
            print("The file was not found")
            return False
        except NoCredentialsError:
            print("Credentials not available")
            return False
    
def Export(UserData):
    Kam = KibanaApiManager()
    KibanaExportManager= Kam.Export(base_url=UserData.get('DashHost'), username=UserData.get('DashUser'), password=UserData.get('DashPass'))
    ExportObj = KibanaExportManager.ExportSavedObjs()
    if ExportObj: #if successfully exported
        Ams= AWSManager(access_key=UserData.get('AccessKey'), secret_key=UserData.get('SecretKey'))
        Ams.DeleteOlderExports(bucket=UserData.get('Bucket'))
        x = Ams.UploadToAws(local_file=ExportObj.get('fileName'), bucket=UserData.get('Bucket')) #upload to S3
def Import(UserData):
    #Download from s3 if there is a newer export
    Ams= AWSManager(access_key=UserData.get('AccessKey'), secret_key=UserData.get('SecretKey'))

    #List all bucket saved objects
    bucket_objects = Ams.ListBucketObjects(bucket=UserData.get('Bucket'))
    get_last_modified = lambda obj: int(obj['LastModified'].strftime('%s'))
    latest_object = [obj['Key'] for obj in sorted(bucket_objects, key=get_last_modified, reverse=True)][0] #Get the latest file in s3
    aws_latest_ts =re.sub('dash-export-', '', latest_object)
    aws_latest_ts =re.sub('.ndjson.gz', '', aws_latest_ts)
    #check local_registry
    try:
        with open("local_registry.txt", "r") as registry_file:
            lines = registry_file.readlines()
            registry_latest_ts = lines[-1]
            registry_latest_ts = re.sub('dash-export-', '', registry_latest_ts)
            registry_latest_ts = re.sub('.ndjson.gz', '', registry_latest_ts)
            if aws_latest_ts > registry_latest_ts: #if local file is newer
                dl_status = Ams.DownloadFromAws(latest_object, UserData.get('Bucket')) #if False, doesn't import to AWS
                # #import to Kibana Instance
                if dl_status:
                    Kam = KibanaApiManager()
                    KibanaImportManager= Kam.Import(base_url= UserData.get('DashHost'), username= UserData.get('DashUser'), password= UserData.get('DashPass'))
                    ImportResponse = KibanaImportManager.ImportDownloadedObjs(FileName=latest_object, domain=UserData.get('UserWebsite'))
            else:
                print("Didnt import because latest file in AWS is less than or equal to the latest version of the last import")
                return False
    except: #if local registry doest not exist
        dl_status = Ams.DownloadFromAws(latest_object, UserData.get('Bucket')) #if False, doesn't import to AWS
        #import to Kibana Instance
        if dl_status:
            Kam = KibanaApiManager()
            KibanaImportManager= Kam.Import(base_url= UserData.get('DashHost'), username= UserData.get('DashUser'), password= UserData.get('DashPass'))
            ImportResponse = KibanaImportManager.ImportDownloadedObjs(FileName=latest_object, domain=UserData.get('UserWebsite'))
            print(ImportResponse)
        else:
            return

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--function", help="Enter Kibana API function", required=True)
    parser.add_argument("-a", "--AccessKeyID", help="Enter AWS access key ID", required=True)
    parser.add_argument("-s","--SecretAccessKey", help="Enter AWS secret access key", required=True)
    parser.add_argument("-b","--bucket", help="Enter the S3 bucket name", required=True)
    parser.add_argument("-u", "--dashuser", help="Enter Kibana dashboard username", required=True)
    parser.add_argument("-p", "--dashpass", help="Enter Kibana dashboard password", required=True)
    parser.add_argument("-H", "--dashhost", help="Enter URL for Kibana API", required=True)
    parser.add_argument("-w", "--UserWebsite", help="Enter URL for Kibana API")
    args = parser.parse_args()


    json_obj = {}
    json_obj['Action'] = args.function
    json_obj['AccessKey'] = args.AccessKeyID
    json_obj['SecretKey'] = args.SecretAccessKey
    json_obj['Bucket'] = args.bucket
    json_obj['DashUser'] = args.dashuser
    json_obj['DashPass'] = args.dashpass
    json_obj['DashHost'] = args.dashhost
    json_obj['UserWebsite'] = args.UserWebsite


    if json_obj.get('Action') == 'export':
        Export(json_obj)

    if json_obj.get('Action') == 'import':
        Import(json_obj)