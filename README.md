# Kibana Dashsync
Script to export kibana dashboards and upload it to s3 bucket and download the latest file from an s3 bucket and import it to the Kibana instance.
### Script Arguments:
- -f = action (import or export)
- -a = AwsAccessKeyID
- -s = AwsSecretAccessKey
- -b = AwsS3BucketName
- -u = KibanaDashUser
- -p = KibanaDashPassword
- -H = KibanaDashHostUrl
- -w = UserWebsite

### Example command to export Kibana dashboard and upload to Amazon S3 Bucket
```python
    python3 dashsync.py -f export -a "{AWS_AccessKeyID}" -s "{AWS_SecretAccessKey}" -u "{KibanaDashUser}" -p {KibanaDashPassword} -H {KibanaAPIBaseUrl} -b {s3_bucket_name}
```

### Example command to download latest export file from s3 bucket and import it to the Kibana instance
```python
    python3 dashsync.py -f import -a "{AWS_AccessKeyID}" -s "{AWS_SecretAccessKey}" -u "{KibanaDashUser}" -p {KibanaDashPassword} -H {KibanaAPIBaseUrl} -b {s3_bucket_name} -w {user_website}
```