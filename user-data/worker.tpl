#!/bin/bash
set -e

exec > >(tee -a /var/log/user-data.log)
exec 2>&1

echo "Starting Worker setup at $(date)"

yum update -y
yum install -y mariadb105-server wget

systemctl start mariadb
systemctl enable mariadb

mysql -u root <<'MYSQL_SETUP'
ALTER USER 'root'@'localhost' IDENTIFIED BY 'Root123!';
CREATE USER 'app_user'@'%' IDENTIFIED BY 'Mehdi1603!';
GRANT ALL PRIVILEGES ON *.* TO 'app_user'@'%';
FLUSH PRIVILEGES;
MYSQL_SETUP

RANDOM_SERVER_ID=$((RANDOM % 1000 + 2))
cat >> /etc/my.cnf.d/server.cnf <<MYSQL_CONFIG
[mysqld]
server-id=${RANDOM_SERVER_ID}
relay-log=mysql-relay-bin
log-bin=mysql-bin
binlog-format=ROW
bind-address=0.0.0.0
read-only=1
MYSQL_CONFIG

systemctl restart mariadb

sleep 10

echo "Installing Sakila database..."
cd /tmp
wget https://downloads.mysql.com/docs/sakila-db.tar.gz
tar -xzf sakila-db.tar.gz
cd sakila-db

mysql -u root -pRoot123! <<'SAKILA_INSTALL'
SOURCE sakila-schema.sql;
SOURCE sakila-data.sql;
SAKILA_INSTALL

echo "Sakila database installed successfully"

yum install -y sysbench

sysbench /usr/share/sysbench/oltp_read_only.lua \
    --mysql-db=sakila \
    --mysql-user=app_user \
    --mysql-password=Mehdi1603! \
    prepare

echo "Sysbench preparation completed"

sleep 30

MANAGER_HOST="{MANAGER_HOST}"
mysql -u root -pRoot123! <<REPLICATION_SETUP
CHANGE MASTER TO
  MASTER_HOST='${MANAGER_HOST}',
  MASTER_USER='replication_user',
  MASTER_PASSWORD='Repl123!',
  MASTER_LOG_FILE='mysql-bin.000001',
  MASTER_LOG_POS=4;
START SLAVE;
REPLICATION_SETUP

touch /tmp/worker_setup_complete
echo "Worker setup completed at $(date)"