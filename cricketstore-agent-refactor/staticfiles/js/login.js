document.addEventListener('DOMContentLoaded',function(){
    const loginForm=document.getElementById('login-form');
    loginForm.addEventListener('submit',function(e){
        e.preventDefault()
        function getCookie(name) {
            let cookieArr = document.cookie.split(";");
            for (let i = 0; i < cookieArr.length; i++) {
                let cookiePair = cookieArr[i].split("=");
                if (name == cookiePair[0].trim()) {
                    return decodeURIComponent(cookiePair[1]);
                }
            }
            return null;
        }

        const csrftoken = getCookie('csrftoken');
        const formData = new FormData(loginForm);
        const jsonData = {};
        formData.forEach((value, key) => {
            jsonData[key] = value;
        });
        fetch('/login/',{
            method:'POST',
            headers:{
                'content-Type':'application/json',
                'X-CSRFToken':csrftoken,
            },
            body:JSON.stringify(jsonData)
        })
        .then(response=>{
            if (response.ok){
                window.location.href='/'
            }
        })
        .catch(error=>{
            console.error('login error:',error);
            alert('please check your credentials');
        });
            
        
    });
});