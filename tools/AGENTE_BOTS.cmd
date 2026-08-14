@echo off
chcp 65001 >nul
title Agente de bots SINAC OS - HUS
cd /d %~dp0..
echo ============================================
echo   AGENTE DE BOTS SINAC OS (PC del HUS)
echo   Usa la misma URL y token del agente de lotes.
echo ============================================
py tools\agente_bots_hus.py
pause
