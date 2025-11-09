import boto3
import configparser
import sys
import os
from mypy_boto3_ec2 import EC2Client

EC2_CLIENT: EC2Client | None = None


"""
    AWS SETUP
"""
def verify_aws_credentials():
    print('- verifying aws credentials')
    
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
            
        except Exception:
            print('- credential verification failed')
            print('- please try again.\n')
            aws_access_key_id, aws_secret_access_key, aws_session_token = get_user_credentials()

    os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key_id
    os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_access_key
    if aws_session_token:
        os.environ['AWS_SESSION_TOKEN'] = aws_session_token
    
    print('- AWS credentials verified')


def get_user_credentials():
    print("- please enter your AWS credentials:")
    aws_access_key_id = input("- AWS access key id: ").strip()
    aws_secret_access_key = input("- AWS secret access key: ").strip()
    aws_session_token = input("- AWS Session Token (press Enter if none): ").strip() or None
    return aws_access_key_id, aws_secret_access_key, aws_session_token


def set_clients():
    print('- starting setting up the boto3 clients')
    try:
        global EC2_CLIENT
        EC2_CLIENT = boto3.client(
            'ec2',
            aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token = os.getenv('AWS_SESSION_TOKEN'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )
        print('- finished setting up the boto3 clients')
    except Exception:
        print('- failed to set the boto3 clients')
        sys.exit(1)


"""
    MySQL Standalone and Sakila
"""
def create_vpc(vpcName: str = 'db-cluster-vpc') -> str:
    print(f'- creating new vpc {vpcName}')
    try:
        response = EC2_CLIENT.create_vpc(
            CidrBlock='10.0.0.0/16',
            TagSpecifications=[
                {
                    'ResourceType': 'vpc',
                    'Tags':[
                        {
                            'Key': 'Name',
                            'Value': vpcName
                        }
                    ]
                }
            ]
        )

        print('- finished creating vpc successfully')
        return response['Vpc']['VpcId']
    except Exception as e:
        print(f'- failed to create vpc {vpcName}: {e}')
        sys.exit(1)


def create_private_subnet(vpcId: str, subnetName: str = 'db-private-subnet') -> str:
    print(f'- creating new private subnet for vpc {vpcId}')
    try:
        response = EC2_CLIENT.create_subnet(
            CidrBlock='10.0.1.0/24',
            VpcId= vpcId,
            
            TagSpecifications=[
                {
                    'ResourceType': 'subnet',
                    'Tags':[{
                        'Key': 'Name',
                        'Value': subnetName
                    }]
                }
            ]
        )

        subnet_id = response['Subnet']['SubnetId']
        EC2_CLIENT.modify_vpc_block_public_access_options(InternetGatewayBlockMode='block-ingress')

        print('- finished creating private subnet successfully')
        return subnet_id
    except Exception:
        print(f'- failed to create private subnet for vpc{vpcId}')
        sys.exit(1)


def create_database_security_group():
    pass


def create_worker_instances(nbr: int) -> list[str]:
    pass


def create_manager_instances(nbr: int) -> list[str]:
    pass


"""
    Proxy
"""


"""
    Gatekeeper
"""


"""
    Benchmark
"""


"""
    Cleanup
"""


def main():

    print('*'*26 + ' BEGINNING AWS SETUP ' + '*'*26)
    verify_aws_credentials()
    set_clients()
    print('*'*26 + '*********************' + '*'*26)
    print('')
    print('*'*25 + ' DEPLOYING MYSQL NODES ' + '*'*25)
    vpc_id = create_vpc()
    custm_private_subnet = create_private_subnet(vpcId=vpc_id)
    print('*'*26 + '*********************' + '*'*26)


if __name__ == '__main__':
    main()