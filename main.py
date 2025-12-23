import boto3
import time
import configparser
import sys
import os
from cleanup import cleanup_all_resources
from benchmark import benchmark_cluster


"""
    AWS SETUP
"""
def validateAWSCredentials():
    try:
        print('- Validating the AWS credentials')

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
            aws_access_key_id, aws_secret_access_key, aws_session_token = getAWSCredentials()

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
                print('- credential verification failed\n')
                aws_access_key_id, aws_secret_access_key, aws_session_token = getAWSCredentials()

        os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key_id
        os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_access_key
        if aws_session_token:
            os.environ['AWS_SESSION_TOKEN'] = aws_session_token

        print('- AWS credentials verified')

    except Exception as e:
        print(f'Failed to validate user\'s credentials: {e}')
        sys.exit(1)


def getAWSCredentials() -> tuple[str, str, str | None]:
    try:
        print('- Enter the following required variables to login')
        aws_access_key_id = input('→ AWS Access Key Id: ')
        aws_secret_access_key = input('→ AWS Secret Access Key: ')
        aws_session_token = input('→ AWS Session Token (press enter if none): ')

        return aws_access_key_id, aws_secret_access_key, aws_session_token
    
    except Exception as e:
        print(f'Failed to get user\'s input credentials: {e}')
        sys.exit(1)


def setBoto3Clients():
    try:
        print('- Starting setting up the boto3 clients')

        global EC2_CLIENT, S3_CLIENT

        EC2_CLIENT = boto3.client(
            'ec2',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )

        S3_CLIENT = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )

        print('- finished setting up the boto3 clients')

    except Exception as e:
        print(f'Failed to set Boto3\'s clients: {e}')
        sys.exit(1)


"""
    Utils Methods
"""
def read_user_data(filename: str, **kwargs) -> str:
    try:
        filepath = os.path.join('user-data', filename)
        with open(filepath, 'r') as f:
            template = f.read()
        
        for key, value in kwargs.items():
            placeholder = f'{{{key.upper()}}}'
            template = template.replace(placeholder, str(value))
        
        return template
    except Exception as e:
        print(f'- error reading user data file {filepath}: {e}')
        sys.exit(1)


def get_instance_private_ip(instance_id):
    response = EC2_CLIENT.describe_instances(InstanceIds=[instance_id])
    return response['Reservations'][0]['Instances'][0]['PrivateIpAddress']


def get_instance_public_ip(instance_id):
    response = EC2_CLIENT.describe_instances(InstanceIds=[instance_id])
    return response['Reservations'][0]['Instances'][0].get('PublicIpAddress', '')


def wait_for_instance_running(instance_ids):
    print(f'- Waiting for instances {instance_ids} to be running...')
    waiter = EC2_CLIENT.get_waiter('instance_running')
    waiter.wait(InstanceIds=instance_ids)
    print(f'- Instances {instance_ids} are now running')


"""
    AWS Entities
"""
def createVPC(cidr_block='10.0.0.0/16', vpc_name='log8415e-vpc'):
    try:
        print(f'- Creating VPC: {vpc_name} with CIDR: {cidr_block}')
        
        vpc_response = EC2_CLIENT.create_vpc(
            CidrBlock=cidr_block,
            TagSpecifications=[
                {
                    'ResourceType': 'vpc',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': vpc_name
                        }
                    ]
                }
            ]
        )
        
        vpc_id = vpc_response['Vpc']['VpcId']
        
        EC2_CLIENT.modify_vpc_attribute(
            VpcId=vpc_id,
            EnableDnsHostnames={'Value': True}
        )
        
        EC2_CLIENT.modify_vpc_attribute(
            VpcId=vpc_id,
            EnableDnsSupport={'Value': True}
        )
        
        print(f'- VPC created successfully with ID: {vpc_id}')
        
        return vpc_id
        
    except Exception as e:
        print(f'- Failed to create VPC {vpc_id}: {e}')
        sys.exit(1)


def createSubnet(vpc_id, cidr_block, availability_zone, subnet_name, is_public=False):
    try:
        print(f'- Creating Subnet: {subnet_name} in {availability_zone}')
        
        subnet_response = EC2_CLIENT.create_subnet(
            VpcId=vpc_id,
            CidrBlock=cidr_block,
            AvailabilityZone=availability_zone,
            TagSpecifications=[
                {
                    'ResourceType': 'subnet',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': subnet_name
                        }
                    ]
                }
            ]
        )
        
        subnet_id = subnet_response['Subnet']['SubnetId']
        
        if is_public:
            EC2_CLIENT.modify_subnet_attribute(
                SubnetId=subnet_id,
                MapPublicIpOnLaunch={'Value': True}
            )
            print(f'- Public Subnet created with ID: {subnet_id}')
        else:
            print(f'- Private Subnet created with ID: {subnet_id}')
        
        return subnet_id
        
    except Exception as e:
        print(f'- Failed to create subnet: {e}')
        sys.exit(1)


def createInternetGateway(vpc_id, igw_name='log8415e-igw'):
    try:
        print(f'- Creating Internet Gateway: {igw_name}')
        
        igw_response = EC2_CLIENT.create_internet_gateway(
            TagSpecifications=[
                {
                    'ResourceType': 'internet-gateway',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': igw_name
                        }
                    ]
                }
            ]
        )
        
        igw_id = igw_response['InternetGateway']['InternetGatewayId']
        
        EC2_CLIENT.attach_internet_gateway(
            InternetGatewayId=igw_id,
            VpcId=vpc_id
        )
        
        print(f'- Internet Gateway created and attached: {igw_id}')
        
        return igw_id
        
    except Exception as e:
        print(f'- Failed to create internet gateway: {e}')
        sys.exit(1)


def createNATGateway(subnet_id, nat_name):
    try:
        print(f'- Creating NAT Gateway: {nat_name}')
        
        eip_response = EC2_CLIENT.allocate_address(Domain='vpc')
        eip_allocation_id = eip_response['AllocationId']
        
        print(f'- Elastic IP allocated: {eip_response["PublicIp"]}')
        
        nat_response = EC2_CLIENT.create_nat_gateway(
            SubnetId=subnet_id,
            AllocationId=eip_allocation_id,
            TagSpecifications=[
                {
                    'ResourceType': 'natgateway',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': nat_name
                        }
                    ]
                }
            ]
        )
        
        nat_gateway_id = nat_response['NatGateway']['NatGatewayId']
        
        print(f'- Waiting for NAT Gateway {nat_name} to become available...')
        waiter = EC2_CLIENT.get_waiter('nat_gateway_available')
        waiter.wait(NatGatewayIds=[nat_gateway_id])
        
        print(f'- NAT Gateway created successfully: {nat_gateway_id}')
        
        return nat_gateway_id
        
    except Exception as e:
        print(f'- Failed to create NAT: {e}')
        sys.exit(1)


def createRoutingTable(vpc_id, igw_id=None, nat_gateway_id=None, route_table_name='route-table', is_public=False):
    try:
        print(f'- Creating Route Table: {route_table_name}')
        
        route_table_response = EC2_CLIENT.create_route_table(
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    'ResourceType': 'route-table',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': route_table_name
                        }
                    ]
                }
            ]
        )
        
        route_table_id = route_table_response['RouteTable']['RouteTableId']
        
        if is_public and igw_id:
            EC2_CLIENT.create_route(
                RouteTableId=route_table_id,
                DestinationCidrBlock='0.0.0.0/0',
                GatewayId=igw_id
            )

            print(f'- Public Route Table created with route to IGW: {route_table_id}')

        elif not is_public and nat_gateway_id:
            EC2_CLIENT.create_route(
                RouteTableId=route_table_id,
                DestinationCidrBlock='0.0.0.0/0',
                NatGatewayId=nat_gateway_id
            )

            print(f'- Private Route Table created with route to NAT: {route_table_id}')
        else:
            print(f'- Route Table created without internet route: {route_table_id}')
        
        return route_table_id
        
    except Exception as e:
        print(f'- Failed to create routing table: {e}')
        sys.exit(1)


def associateRouteTable(route_table_id, subnet_id):
    try:
        print(f'- Associating Route Table {route_table_id} with Subnet {subnet_id}')
        
        association_response = EC2_CLIENT.associate_route_table(
            RouteTableId=route_table_id,
            SubnetId=subnet_id
        )
        
        association_id = association_response['AssociationId']
        print(f'- Route Table associated successfully: {association_id}')
        
        return association_id
        
    except Exception as e:
        print(f'- Failed to associate route table: {e}')
        sys.exit(1)


def createSecurityGroup(vpc_id, sg_name='log8415e-sg', sg_description='Security group for final assignment', ingress_rules=None, egress_rules=None):
    try:
        print(f'- Creating Security Group: {sg_name}')
        
        sg_response = EC2_CLIENT.create_security_group(
            GroupName=sg_name,
            Description=sg_description,
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    'ResourceType': 'security-group',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': sg_name
                        }
                    ]
                }
            ]
        )
        
        security_group_id = sg_response['GroupId']
        
        if ingress_rules:
            print('- Adding ingress rules to Security Group')
            for rule in ingress_rules:
                EC2_CLIENT.authorize_security_group_ingress(
                    GroupId=security_group_id,
                    IpPermissions=[
                        {
                            'IpProtocol': rule['IpProtocol'],
                            'FromPort': rule['FromPort'],
                            'ToPort': rule['ToPort'],
                            'IpRanges': [{'CidrIp': rule['CidrIp'], 'Description': rule['Description']}]
                        }
                    ]
                )
        
        if egress_rules:
            print('- Adding egress rules to Security Group')
            try:
                EC2_CLIENT.revoke_security_group_egress(
                    GroupId=security_group_id,
                    IpPermissions=[
                        {
                            'IpProtocol': '-1',
                            'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                        }
                    ]
                )
            except Exception as e:
                print(f'- Note: Could not remove default egress rule: {e}')
            
            for rule in egress_rules:
                EC2_CLIENT.authorize_security_group_egress(
                    GroupId=security_group_id,
                    IpPermissions=[
                        {
                            'IpProtocol': rule['IpProtocol'],
                            'FromPort': rule['FromPort'],
                            'ToPort': rule['ToPort'],
                            'IpRanges': [{'CidrIp': rule['CidrIp'], 'Description': rule['Description']}]
                        }
                    ]
                )
        
        print(f'- Security Group created successfully: {security_group_id}')
        
        return security_group_id
        
    except Exception as e:
        print(f'- Failed to create security group: {e}')
        sys.exit(1)


def createEC2Instance(
    subnet_id,
    instance_type,
    ami_id='ami-0157af9aea2eef346',
    instance_name='instance',
    security_group_id=None,
    user_data=None,
    count=1
):
    try:
        print(f'- Creating {count} EC2 instance(s): {instance_name}')
        
        run_params = {
            'ImageId': ami_id,
            'InstanceType': instance_type,
            'SubnetId': subnet_id,
            'MinCount': count,
            'MaxCount': count,
        }
        
        if security_group_id:
            run_params['SecurityGroupIds'] = [security_group_id]
        
        if user_data:
            run_params['UserData'] = user_data
        
        response = EC2_CLIENT.run_instances(**run_params)
        
        instance_ids = [instance['InstanceId'] for instance in response['Instances']]

        for i, instance_id in enumerate(instance_ids):
            tag_name = instance_name if count == 1 else f'{instance_name}-{i+1}'
            EC2_CLIENT.create_tags(
                Resources=[instance_id],
                Tags=[
                    {
                        'Key': 'Name',
                        'Value': tag_name
                    }
                ]
            )
        
        print(f'- Created instance(s) successfully: {instance_ids}')
        
        return instance_ids
        
    except Exception as e:
        print(f'- Failed to create EC2 instance: {e}')
        sys.exit(1)


def create_s3_bucket(bucket_name):
    try:
        print(f'- Creating S3 bucket: {bucket_name}')
        
        S3_CLIENT.create_bucket(Bucket=bucket_name)
        
        print(f'- S3 bucket created successfully: {bucket_name}')
        return bucket_name
        
    except S3_CLIENT.exceptions.BucketAlreadyOwnedByYou:
        print(f'- S3 bucket {bucket_name} already exists and is owned by you')
        return bucket_name
    except Exception as e:
        print(f'- Failed to create S3 bucket: {e}')
        sys.exit(1)


"""
    MySQL Standalone and Sakila
"""
def create_manager_instances(nbrInstances: int, vpcId: str, subnetId: str, private_subnet_cidr: str) -> tuple[list[str], list[str]]:
    print(f'- creating {nbrInstances} new manager instances')

    ingress = [
        {
            'IpProtocol': 'tcp',
            'FromPort': 3306,
            'ToPort': 3306,
            'CidrIp': private_subnet_cidr,
            'Description': 'MySQL access from Proxy for WRITE queries'
        },
        {
            'IpProtocol': 'icmp',
            'FromPort': -1,
            'ToPort': -1,
            'CidrIp': private_subnet_cidr,
            'Description': 'ICMP for ping checks from Proxy'
        }
    ]

    egress = [
        {
            'IpProtocol': 'tcp',
            'FromPort': 443,
            'ToPort': 443,
            'CidrIp': '0.0.0.0/0',
            'Description': 'HTTPS outbound for package updates'
        },
        {
            'IpProtocol': 'tcp',
            'FromPort': 80,
            'ToPort': 80,
            'CidrIp': '0.0.0.0/0',
            'Description': 'HTTP outbound for package updates'
        },
        {
            'IpProtocol': 'tcp',
            'FromPort': 3306,
            'ToPort': 3306,
            'CidrIp': private_subnet_cidr,
            'Description': 'MySQL replication traffic to workers'
        }
    ]

    userData = read_user_data('manager.tpl')

    sgId = createSecurityGroup(
        vpc_id=vpcId,
        sg_name='manager-sg',
        sg_description='Security group for MySQL manager node',
        ingress_rules=ingress,
        egress_rules=egress
    )
    
    instancesId = createEC2Instance(
        subnet_id=subnetId,
        instance_type='t2.micro',
        instance_name='mysql-manager',
        security_group_id=sgId,
        user_data=userData,
        count=1
    )
    
    wait_for_instance_running(instancesId)
    
    instance_ips = [get_instance_private_ip(iid) for iid in instancesId]
    
    print(f'- Manager instances created: {instancesId}')
    print(f'- Manager IPs: {instance_ips}')
    
    return instancesId, instance_ips


def create_worker_instances(nbrInstances: int, vpcId: str, subnetId: str, private_subnet_cidr: str, manager_ip: str) -> tuple[list[str], list[str]]:
    print(f'- creating {nbrInstances} new worker instances')

    ingress = [
        {
            'IpProtocol': 'tcp',
            'FromPort': 3306,
            'ToPort': 3306,
            'CidrIp': private_subnet_cidr,
            'Description': 'MySQL access from Proxy for READ queries'
        },
        {
            'IpProtocol': 'icmp',
            'FromPort': -1,
            'ToPort': -1,
            'CidrIp': private_subnet_cidr,
            'Description': 'ICMP for ping checks from Proxy'
        }
    ]

    egress = [
        {
            'IpProtocol': 'tcp',
            'FromPort': 443,
            'ToPort': 443,
            'CidrIp': '0.0.0.0/0',
            'Description': 'HTTPS outbound for package updates'
        },
        {
            'IpProtocol': 'tcp',
            'FromPort': 80,
            'ToPort': 80,
            'CidrIp': '0.0.0.0/0',
            'Description': 'HTTP outbound for package updates'
        },
        {
            'IpProtocol': 'tcp',
            'FromPort': 3306,
            'ToPort': 3306,
            'CidrIp': private_subnet_cidr,
            'Description': 'MySQL replication traffic from manager'
        }
    ]

    userData = read_user_data('worker.tpl', manager_host=manager_ip)
    
    sgId = createSecurityGroup(
        vpc_id=vpcId,
        sg_name='worker-sg',
        sg_description='Security group for MySQL worker nodes',
        ingress_rules=ingress,
        egress_rules=egress
    )

    instancesId = createEC2Instance(
        subnet_id=subnetId,
        instance_type='t2.micro',
        instance_name='mysql-worker',
        security_group_id=sgId,
        user_data=userData,
        count=nbrInstances
    )
    
    wait_for_instance_running(instancesId)
    
    instance_ips = [get_instance_private_ip(iid) for iid in instancesId]
    
    print(f'- Worker instances created: {instancesId}')
    print(f'- Worker IPs: {instance_ips}')
    
    return instancesId, instance_ips


"""
    Proxy
"""
def create_proxy_instance(vpcId: str, subnetId: str, public_subnet_cidr: str, private_subnet_cidr: str, manager_ip: str, worker_ips: list[str]) -> tuple[str, str]:
    print('- Creating Proxy instance')
    
    ingress = [
        {
            'IpProtocol': 'tcp',
            'FromPort': 5000,
            'ToPort': 5000,
            'CidrIp': public_subnet_cidr,
            'Description': 'Proxy API access from Gatekeeper only'
        }
    ]

    egress = [
        {
            'IpProtocol': 'tcp',
            'FromPort': 443,
            'ToPort': 443,
            'CidrIp': '0.0.0.0/0',
            'Description': 'HTTPS outbound for package updates'
        },
        {
            'IpProtocol': 'tcp',
            'FromPort': 80,
            'ToPort': 80,
            'CidrIp': '0.0.0.0/0',
            'Description': 'HTTP outbound for package updates'
        },
        {
            'IpProtocol': 'tcp',
            'FromPort': 3306,
            'ToPort': 3306,
            'CidrIp': private_subnet_cidr,
            'Description': 'MySQL access to database cluster in private subnet'
        },
        {
            'IpProtocol': 'icmp',
            'FromPort': -1,
            'ToPort': -1,
            'CidrIp': private_subnet_cidr,
            'Description': 'ICMP for ping checks to workers and manager'
        }
    ]
    
    worker_hosts_str = ','.join(worker_ips)
    userData = read_user_data('proxy.tpl', manager_host=manager_ip, worker_hosts=worker_hosts_str)

    sgId = createSecurityGroup(
        vpc_id=vpcId,
        sg_name='proxy-sg',
        sg_description='Security group for Proxy (Trusted Host) - NOT internet-facing',
        ingress_rules=ingress,
        egress_rules=egress
    )
    
    instancesId = createEC2Instance(
        subnet_id=subnetId,
        instance_type='t2.large',
        instance_name='proxy-trusted-host',
        security_group_id=sgId,
        user_data=userData,
        count=1
    )
    
    wait_for_instance_running(instancesId)
    
    proxy_ip = get_instance_private_ip(instancesId[0])
    
    print(f'- Proxy instance created: {instancesId[0]}')
    print(f'- Proxy IP: {proxy_ip}')

    return instancesId[0], proxy_ip


"""
    Gatekeeper
"""
def create_gatekeeper_instance(vpcId: str, subnetId: str, private_subnet_cidr: str, proxy_ip: str) -> tuple[str, str]:
    print('- Creating Gatekeeper instance')
    
    ingress = [
        {
            'IpProtocol': 'tcp',
            'FromPort': 80,
            'ToPort': 80,
            'CidrIp': '0.0.0.0/0',
            'Description': 'HTTP access from internet'
        },
        {
            'IpProtocol': 'tcp',
            'FromPort': 443,
            'ToPort': 443,
            'CidrIp': '0.0.0.0/0',
            'Description': 'HTTPS access from internet'
        },
        {
            'IpProtocol': 'tcp',
            'FromPort': 22,
            'ToPort': 22,
            'CidrIp': '0.0.0.0/0',
            'Description': 'SSH access for management'
        },
        {
            'IpProtocol': 'tcp',
            'FromPort': 8080,
            'ToPort': 8080,
            'CidrIp': '0.0.0.0/0',
            'Description': 'HTTP access from internet'
        },
    ]

    egress = [
        {
            'IpProtocol': 'tcp',
            'FromPort': 443,
            'ToPort': 443,
            'CidrIp': '0.0.0.0/0',
            'Description': 'HTTPS outbound for package updates'
        },
        {
            'IpProtocol': 'tcp',
            'FromPort': 80,
            'ToPort': 80,
            'CidrIp': '0.0.0.0/0',
            'Description': 'HTTP outbound for package updates'
        },
        {
            'IpProtocol': 'tcp',
            'FromPort': 5000,
            'ToPort': 5000,
            'CidrIp': private_subnet_cidr,
            'Description': 'Forwarding validated requests to Proxy'
        }
    ]

    userData = read_user_data('gatekeeper.tpl', proxy_host=proxy_ip)

    sgId = createSecurityGroup(
        vpc_id=vpcId,
        sg_name='gatekeeper-sg',
        sg_description='Security group for Gatekeeper - Internet-facing',
        ingress_rules=ingress,
        egress_rules=egress
    )
    
    instancesId = createEC2Instance(
        subnet_id=subnetId,
        instance_type='t2.large',
        instance_name='gatekeeper',
        security_group_id=sgId,
        user_data=userData,
        count=1
    )
    
    wait_for_instance_running(instancesId)
    
    gatekeeper_ip = get_instance_public_ip(instancesId[0])
    
    print(f'- Gatekeeper instance created: {instancesId[0]}')
    print(f'- Gatekeeper public IP: {gatekeeper_ip}')
    
    return instancesId[0], gatekeeper_ip


def main():
    print('')
    print('*'*16 + ' AWS BOTO3 SCRIPT ' + '*'*16)
    validateAWSCredentials()
    setBoto3Clients()
    print('*'*50 + '\n')

    VPC_CIDR = '10.0.0.0/16'
    PUBLIC_SUBNET_CIDR = '10.0.1.0/24'
    PRIVATE_SUBNET_CIDR = '10.0.2.0/24'
    AVAILABILITY_ZONE = 'us-east-1a'


    print('*'*16 + ' CREATION INFRA ' + '*'*18)
    vpc_id = createVPC(cidr_block=VPC_CIDR, vpc_name='mysql-cluster-vpc')

    public_subnet_id = createSubnet(
        vpc_id=vpc_id,
        cidr_block=PUBLIC_SUBNET_CIDR,
        availability_zone=AVAILABILITY_ZONE,
        subnet_name='public-subnet',
        is_public=True
    )
    
    private_subnet_id = createSubnet(
        vpc_id=vpc_id,
        cidr_block=PRIVATE_SUBNET_CIDR,
        availability_zone=AVAILABILITY_ZONE,
        subnet_name='private-subnet',
        is_public=False
    )

    igw_id = createInternetGateway(vpc_id=vpc_id, igw_name='mysql-cluster-igw')
    nat_gateway_id = createNATGateway(subnet_id=public_subnet_id, nat_name='mysql-cluster-nat')

    public_route_table_id = createRoutingTable(
        vpc_id=vpc_id,
        igw_id=igw_id,
        route_table_name='public-route-table',
        is_public=True
    )
    
    private_route_table_id = createRoutingTable(
        vpc_id=vpc_id,
        nat_gateway_id=nat_gateway_id,
        route_table_name='private-route-table',
        is_public=False
    )
    
    associateRouteTable(public_route_table_id, public_subnet_id)
    associateRouteTable(private_route_table_id, private_subnet_id)

    manager_ids, manager_ips = create_manager_instances(
        nbrInstances=1,
        vpcId=vpc_id,
        subnetId=private_subnet_id,
        private_subnet_cidr=PRIVATE_SUBNET_CIDR
    )
    
    worker_ids, worker_ips = create_worker_instances(
        nbrInstances=2,
        vpcId=vpc_id,
        subnetId=private_subnet_id,
        private_subnet_cidr=PRIVATE_SUBNET_CIDR,
        manager_ip=manager_ips[0]
    )

    proxy_id, proxy_ip = create_proxy_instance(
        vpcId=vpc_id,
        subnetId=private_subnet_id,
        public_subnet_cidr=PUBLIC_SUBNET_CIDR,
        private_subnet_cidr=PRIVATE_SUBNET_CIDR,
        manager_ip=manager_ips[0],
        worker_ips=worker_ips
    )

    gatekeeper_id, gatekeeper_public_ip = create_gatekeeper_instance(
        vpcId=vpc_id,
        subnetId=public_subnet_id,
        private_subnet_cidr=PRIVATE_SUBNET_CIDR,
        proxy_ip=proxy_ip
    )

    print('*'*50 + '\n')

    print('*'*16 + ' RESULTS OF INFRA ' + '*'*16)

    print(f'- manager:, {manager_ids[0]}: {manager_ips[0]}')

    for i, (wid, wip) in enumerate(zip(worker_ids, worker_ips), 1):
        print(f'- worker-{i}, {wid}: {wip}')

    print(f'- proxy, {proxy_id}: {proxy_ip}')

    print(f'- gatekeeper, {gatekeeper_id}: {gatekeeper_public_ip}')

    print('*'*50 + '\n')

    print('*'*16 + ' BENCHMARKING ' + '*'*20)
    print('-Waiting for 2min so the instances are ready...')
    time.sleep(120)
    benchmark_cluster(
    gatekeeper_ip=gatekeeper_public_ip,
    manager_ip=manager_ips[0],
    worker_ips=worker_ips,
    api_key="test-api-key"
)
    print('*'*50 + '\n')

    print('*'*16 + ' CLEANUP SCRIPT ' + '*'*18)
    print('-Cleanup will start in 2min...')
    time.sleep(120)
    cleanup_all_resources(EC2_CLIENT, vpc_id=vpc_id)
    print('*'*50 + '\n')


if __name__ == '__main__':
    main()