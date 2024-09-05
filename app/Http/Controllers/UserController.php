<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use App\Models\User;
use Illuminate\Support\Facades\Hash;
class UserController extends Controller
{
    public function register( Request $request ){
     $fields=$request->validate([
     'name'=>'required|string',
     'email'=>'required|string|unique:users,email',
     'password'=>'required|string|confirmed',
     ]);
     $user=User::create([
     'name'=>$fields['name'],
     'email'=>$fields['email'],
     'password'=>bcrypt($fields['password']),
   
     ]);
     $token=$user->createToken('myapptoken')->plainTextToken;

     $respons=[
      'user'=>$user,
      'token'=>$token,
       'massage'=>'sucsess',
     ];
     return response($respons,201);
    }

    public function login(Request $request){

        $fields=$request->validate([
            'email'=>'required|string',
            'password'=>'required|string',
            ]);

        $user=User::where('email',$fields['email'])->first();
        if(!$user||!Hash::check($fields['password'],$user->password))
        {
           return response([
            'message'=>'Bad creds'
           ],401  );
        }
          $token=$user->createToken('myapptoken')->plainTextToken;
          $response=[
              'user'=>$user,
              'token'=>$token,
              'message' => 'success',
        
          ];
        
          return response($response,201);
        
        }
    public function logout(Request $request){
        $request->user()->currentAccessToken()->delete();
        return response()->json(['message' => 'success'], 200);
      
   }
   public function DeleteAcount(Request $request){
    $request->user()->currentAccessToken()->delete();
    $request->user()->delete();
    return response()->json(['message' => 'success'], 200);
   }
}
