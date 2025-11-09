import boto3
import configparser
import sys
import os
from mypy_boto3_ec2 import EC2Client


EC2_CLIENT: EC2Client | None = None


"""
    Utility Methods
"""
def read_user_data(filename: str) -> str:
    try:
        filepath = os.path.join('user-data', filename)
        with open(filepath, 'r') as f:
            return f.read()
        
    except Exception:
        print(f'- error reading user data file {filepath}')
        sys.exit(1)
 
    
def create_security_group(sgName: str, vpcId: str,ingressRules: list[str], egressRules: list[str],  desc: str = '') -> str:
    print(f'- creating new security group {sgName}')
    try:
        response = EC2_CLIENT.create_security_group(
            GroupName=sgName,
            Description=desc,
            VpcId= vpcId
        )

        sgId = response['GroupId']

        if ingressRules:
            EC2_CLIENT.authorize_security_group_ingress(
                GroupId= sgId,
                IpPermissions=ingressRules
            )

        if egressRules:
            EC2_CLIENT.authorize_security_group_egress(
                GroupId= sgId,
                IpPermissions=egressRules
            )

        print(f'- created security group {sgName} successfully')
        return sgId
    except Exception:
        print(f'- failed to create security group {sgName}')
        sys.exit(1)
    

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


def get_user_credentials() -> tuple[str, str, str | None]:
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

        subnetId = response['Subnet']['SubnetId']
        EC2_CLIENT.modify_vpc_block_public_access_options(InternetGatewayBlockMode='block-ingress')

        print('- finished creating private subnet successfully')
        return subnetId
    except Exception:
        print(f'- failed to create private subnet for vpc{vpcId}')
        sys.exit(1)


def create_worker_instances(nbrInstances: int, vpcId: str, subnetId: str,) -> list[str]:
    print('- creating new worker instances')
    instancesId = []

    ingress = []
    egress = []
    userData = read_user_data('worker.tpl')
    sgId = create_security_group(sgName='sg-workers', vpcId= vpcId, ingressRules= ingress, egressRules=egress)
    try:
        response = EC2_CLIENT.run_instances(
            ImageId= 'ami-0157af9aea2eef346',
            InstanceType= 't2.micro',
            SubnetId= subnetId,
            SecurityGroupIds= [sgId],
            MinCount= nbrInstances,
            MaxCount= nbrInstances,
            UserData= userData,
            TagSpecifications= [
                {
                    'ResourceType': 'instance',
                    'Tags':[
                        {
                            'Key': 'Name',
                            'Value': f'worker-{i+1}'
                        } for i in range(nbrInstances)
                    ]
                }
            ]
        )

        instancesId = [instance['InstanceId'] for instance in response['Instances']]
        print(f'- created {nbrInstances} worker instances successfully')
        return instancesId

    except Exception:
        print('- failed to create worker instances')
        sys.exit(1)


def create_manager_instances(nbrInstances: int, vpcId: str, subnetId: str,) -> list[str]:
    print('- creating new manager instances')
    instancesId = []

    ingress = []
    egress = []
    userData = read_user_data('manager.tpl')
    sgId = create_security_group(sgName='sg-managers', vpcId= vpcId, ingressRules= ingress, egressRules=egress)
    try:
        response = EC2_CLIENT.run_instances(
            ImageId= 'ami-0157af9aea2eef346',
            InstanceType= 't2.micro',
            SubnetId= subnetId,
            SecurityGroupIds= [sgId],
            MinCount= nbrInstances,
            MaxCount= nbrInstances,
            UserData= userData,
            TagSpecifications= [
                {
                    'ResourceType': 'instance',
                    'Tags':[
                        {
                            'Key': 'Name',
                            'Value': f'manager-{i+1}'
                        } for i in range(nbrInstances)
                    ]
                }
            ]
        )

        instancesId = [instance['InstanceId'] for instance in response['Instances']]
        print(f'- created {nbrInstances} manager instances successfully')
        return instancesId

    except Exception:
        print('- failed to create manager instances')
        sys.exit(1)


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
    print('*'*26 + ' DEPLOYING INFRASTRUCTURE' + '*'*21)
    vpc_id = create_vpc()
    private_subnet_id = create_private_subnet(vpcId=vpc_id)
    print('*'*26 + '*********************' + '*'*26)


if __name__ == '__main__':
    main()