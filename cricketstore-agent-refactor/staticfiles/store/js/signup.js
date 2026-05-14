document.addEventListener('DOMContentLoaded',function(){
    const signupform=document.getElementById('signup-form');
    signupform.addEventListener('submit',function(e){
        e.preventDefault();
        function gettoken(name){
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
        const formdata=new FormData(signupform)
        const jsonData = {};

        formdata.forEach((value, key) => {
            jsonData[key] = value;
        });
        fetch('/signup/',{
            method:POST,
            headers:{
                'Content-Type':'application/json',
                'X-CSRFToken': csrftoken
            },
            body:JSON.stringify(jsonData)

        })
        .then(respose=>{
            if (Response.ok){
                window.location.href='/login/'
            }else{
                return response.json().then(data => {
                    alert('Signup failed: ' + (data.error || 'Unknown error'));
                });
            }
        })
        .catch(error=>{
            console.error('Error:',error)
        });

    });
});