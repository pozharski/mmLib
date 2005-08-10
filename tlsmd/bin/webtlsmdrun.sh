#!/bin/bash

export TLSMD_ROOT=/home/tlsmd/tlsmd
export LOG_ROOT=$TLSMD_ROOT/log
#export TLSMD_GRID_FILE=$TLSMD_ROOT/data/grid.cfg

## start two computation servers
$TLSMD_ROOT/bin/tlsmdgridd.py 9600 > $LOG_ROOT/server1.log      2>&1 & 
$TLSMD_ROOT/bin/tlsmdgridd.py 9601 > $LOG_ROOT/server2.log      2>&1 & 
sleep 1

## start web-app database server daemon
$TLSMD_ROOT/bin/webtlsmdd.py     > $LOG_ROOT/webtlsmdd.log    2>&1 &
sleep 1

## start the web-app tlsmd job running daemon
$TLSMD_ROOT/bin/webtlsmdrund.py  > $LOG_ROOT/webtlsmdrund.log 2>&1 &
