#!/bin/bash
set -e

exec > >(tee -a /var/log/user-data.log)
exec 2>&1

echo "Starting Manager setup at $(date)"

yum update -y
yum install -y mariadb105-server wget

systemctl start mariadb
systemctl enable mariadb

mysql -u root <<'MYSQL_SETUP'
ALTER USER 'root'@'localhost' IDENTIFIED BY 'Root123!';
CREATE USER 'app_user'@'%' IDENTIFIED BY 'Mehdi1603!';
GRANT ALL PRIVILEGES ON *.* TO 'app_user'@'%';
CREATE USER 'replication_user'@'%' IDENTIFIED BY 'Repl123!';
GRANT REPLICATION SLAVE ON *.* TO 'replication_user'@'%';
FLUSH PRIVILEGES;
MYSQL_SETUP

cat >> /etc/my.cnf.d/server.cnf <<'MYSQL_CONFIG'
[mysqld]
server-id=1
log-bin=mysql-bin
binlog-format=ROW
bind-address=0.0.0.0
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

mysql -u root -pRoot123! -e "SHOW MASTER STATUS\G" > /tmp/master_status.txt

touch /tmp/manager_setup_complete
echo "Manager setup completed at $(date)"