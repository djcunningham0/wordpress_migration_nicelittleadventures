# .sql export

1. Go to Siteground -> Websites -> Site Tools -> select MySQL (under Site) on sidebar -> select PHPMYADMIN tab
2. Access phpMyAdmin
3. Select your DB on the left sidebar
4. Click the Export tab on the top
5. Export to SQL format

# WordPress XML export

WordPress admin dashboard -> Tools -> Export -> all content -> download export file

# uploads directory export

1. ssh into siteground: `ssh siteground` (assuming you've configured hostname, user, and port in `~/.ssh/config`)
2. create `.tar.gz` file
    a. `cd www/nicelittleadventures.com/public_html/wp-content/`
    b. `tar -czf uploads.tar.gz uploads`
3. download the `.tar.gz` file: `scp siteground:~/www/nicelittleadventures.com/public_html/wp-content/uploads.tar.gz .`
4. delete the `.tar.gz` file on the server
