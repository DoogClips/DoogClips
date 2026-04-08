@echo off
setlocal
set TARGET=
set /p TARGET=Enter full path to your DoogClips V9 folder (example: C:\Users\YourName\Downloads\DoogClips V9): 

if "%TARGET%"=="" (
  echo No target path provided.
  pause
  exit /b 1
)

echo Copying updated files to %TARGET% ...

if not exist "%TARGET%\doogclips" (
  echo Target folder not found: %TARGET%\doogclips
  pause
  exit /b 1
)

mkdir "%TARGET%\assets\fonts\redditsans" >nul 2>&1
mkdir "%TARGET%\assets\icons\reddit" >nul 2>&1

copy /Y "..\doogclips\reddit_pipeline.py" "%TARGET%\doogclips\reddit_pipeline.py" >nul
copy /Y "..\doogclips\utils\reddit_utils.py" "%TARGET%\doogclips\utils\reddit_utils.py" >nul
copy /Y "..\doogclips\gui\main_window.py" "%TARGET%\doogclips\gui\main_window.py" >nul

copy /Y "..\assets\fonts\redditsans\RedditSans-Regular.ttf" "%TARGET%\assets\fonts\redditsans\RedditSans-Regular.ttf" >nul
copy /Y "..\assets\fonts\redditsans\RedditSans-Medium.ttf" "%TARGET%\assets\fonts\redditsans\RedditSans-Medium.ttf" >nul
copy /Y "..\assets\fonts\redditsans\RedditSans-SemiBold.ttf" "%TARGET%\assets\fonts\redditsans\RedditSans-SemiBold.ttf" >nul
copy /Y "..\assets\fonts\redditsans\RedditSans-Bold.ttf" "%TARGET%\assets\fonts\redditsans\RedditSans-Bold.ttf" >nul

copy /Y "..\assets\icons\reddit\upvote.png" "%TARGET%\assets\icons\reddit\upvote.png" >nul
copy /Y "..\assets\icons\reddit\downvote.png" "%TARGET%\assets\icons\reddit\downvote.png" >nul
copy /Y "..\assets\icons\reddit\comment.png" "%TARGET%\assets\icons\reddit\comment.png" >nul
copy /Y "..\assets\icons\reddit\award.png" "%TARGET%\assets\icons\reddit\award.png" >nul
copy /Y "..\assets\icons\reddit\share.png" "%TARGET%\assets\icons\reddit\share.png" >nul
copy /Y "..\assets\icons\reddit\rslash.png" "%TARGET%\assets\icons\reddit\rslash.png" >nul

echo Done.
pause
endlocal
