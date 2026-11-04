@echo off
setlocal
cd /d "%~dp0"
set "AURORA_ENABLE_TEXT_INPUT_PROCESS=0"
call "%~dp0launch_aurora2.cmd" --with-ui --offline --no-live-init --no-chat-log-echo --no-smoke-test --screenshot-interval 0.35 --review-turn-interval 12 --critique-turn-interval 45 %*
endlocal
