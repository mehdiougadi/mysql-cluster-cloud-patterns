import boto3
import configparser
import os


def verify_aws_credentials():
    print('=== VERIFY AWS CREDENTIALS ===')
    
    aws_access_key_id = None
    aws_secret_access_key = None
    aws_session_token = None
    is_not_valid = True

    credentials_path = os.path.expanduser('~/.aws/credentials')
    config = configparser.ConfigParser()

    if os.path.exists(credentials_path):
        config.read(credentials_path)
        if 'default' in config:
            aws_access_key_id = config['default'].get('aws_access_key_id')
            aws_secret_access_key = config['default'].get('aws_secret_access_key')
            aws_session_token = config['default'].get('aws_session_token')

    if not aws_access_key_id or not aws_secret_access_key:
        aws_access_key_id, aws_secret_access_key, aws_session_token = get_user_credentials()

    while is_not_valid:
        try:
            sts = boto3.client(
                'sts',
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                aws_session_token=aws_session_token
            )
            
            sts.get_caller_identity()
            is_not_valid = False
            
        except Exception as e:
            print(f'Credential verification failed: {e}')
            print('Please try again.\n')
            aws_access_key_id, aws_secret_access_key, aws_session_token = get_user_credentials()

    os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key_id
    os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_access_key
    if aws_session_token:
        os.environ['AWS_SESSION_TOKEN'] = aws_session_token
    
    print('AWS credentials verified')


def get_user_credentials():
    print("Please enter your AWS credentials:")
    aws_access_key_id = input("AWS access key id: ").strip()
    aws_secret_access_key = input("AWS secret access key: ").strip()
    aws_session_token = input("AWS Session Token (press Enter if none): ").strip() or None
    return aws_access_key_id, aws_secret_access_key, aws_session_token


def main():
    verify_aws_credentials()


if __name__ == '__main__':
    main()