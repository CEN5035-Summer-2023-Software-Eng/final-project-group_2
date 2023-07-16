$(document).ready(function(){
    $('#login-form').on('submit', function(e) {
        e.preventDefault();
        $.ajax({
            url: '/',
            data: $('form').serialize(),
            type: 'POST',
            success: function(response) {
                if (response.status == 'success') {
                    window.location.href = "/welcome/" + response.username + "+" + response.token;
                }
            },
            error: function(response) {
                alert(response.responseJSON.message);
            }
        });
    });
});