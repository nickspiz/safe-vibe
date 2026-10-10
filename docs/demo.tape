# Same demo as demo.gif, for charmbracelet/vhs:  vhs docs/demo.tape
# (docs/render_demo.py draws the committed GIF without needing vhs.)
Output docs/demo.gif
Set Shell "bash"
Set FontSize 16
Set Width 960
Set Height 560
Set Padding 20
Set TypingSpeed 40ms
Set Theme "Dracula"
Hide
Type "cd $(mktemp -d) && export HOME=$PWD CLAUDE_PROJECT_DIR=$PWD PS1='$ ' && alias try=$OLDPWD/docs/try.sh && clear"
Enter
Show
Type "try git push --force origin main"
Enter
Sleep 3s
Type 'try psql -c "DROP TABLE users;"'
Enter
Sleep 3s
Type "try git status"
Enter
Sleep 2s
